"""Batch payslip processing routes with stage-level progress."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
    DocumentUploadRejectedError,
)
from payroll_copilot.application.services.batch_progress_store import (
    BatchExtractedItem,
    get_batch_progress_store,
)
from payroll_copilot.application.services.document_upload_guardrail import (
    DocumentUploadGuardrailService,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    fields_from_structured,
    review_fields_from_structured,
)
from payroll_copilot.application.services.dynamic_document import entries_from_structured
from payroll_copilot.application.services.employee_workspace_snapshot import (
    fields_for_workspace_api,
)
from payroll_copilot.application.services.extraction_explainability import (
    attach_field_evidence,
    build_field_evidence_map,
    build_validation_explanation,
    build_validation_run_explanation,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.application.use_cases.documents import UploadDocumentCommand
from payroll_copilot.application.use_cases.publish_batch_payslip import (
    PublishBatchPayslipUseCase,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
)
from payroll_copilot.infrastructure.tasks.batch_pipeline_factory import (
    create_batch_payslip_pipeline,
)
from payroll_copilot.infrastructure.tasks.celery_app import process_bulk_payslip_pdf
from payroll_copilot.presentation.api.dependencies import (
    get_run_persisted_validation_use_case,
)
from payroll_copilot.presentation.api.rate_limit_deps import limit_accountant_upload
from payroll_copilot.presentation.api.upload_limits import read_upload_with_size_limit
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    bind_accountant_selected_employee,
    require_accountant,
)

from payroll_copilot.presentation.api.routes.batch_schemas import (
    BatchExtractedItemResponse,
    BatchItemResolutionRequest,
    BatchItemReviewResponse,
    BatchJobResponse,
    BatchJobStatusResponse,
    BatchPublishResponse,
    BatchReportResponse,
    BatchReviewCorrectionRequest,
    StageProgressResponse,
)


router = APIRouter()



def _require_batch_item(
    batch_job_id: str,
    item_id: str,
    principal: AuthPrincipal,
) -> tuple[object, BatchExtractedItem]:
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None or job.organization_id != str(principal.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch job not found."},
        )
    item = next((row for row in job.items if row.id == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_item_not_found", "message": "Batch item not found."},
        )
    return job, item


@router.post("/payslips", response_model=BatchJobResponse, status_code=202)
async def upload_bulk_payslips(
    file: UploadFile = File(...),
    _: None = Depends(limit_accountant_upload),
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchJobResponse:
    batch_job_id = str(uuid4())
    document_id = str(uuid4())

    settings = get_settings()
    max_size = settings.max_bulk_pdf_size_mb * 1024 * 1024
    content = await read_upload_with_size_limit(file, max_size)
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    try:
        DocumentUploadGuardrailService(settings).validate(
            UploadDocumentCommand(
                content=content,
                original_filename=file.filename or "bulk-payslips.pdf",
                mime_type="application/pdf",
                document_type=DocumentType.BULK_PAYSLIP_PDF,
                organization_id=principal.organization_id,
                uploaded_by_user_id=principal.user_id,
            )
        )
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": str(exc)},
        ) from exc
    storage = create_object_storage(settings)
    await storage.upload(f"documents/{document_id}", content, "application/pdf")

    store = get_batch_progress_store()
    store.create(
        batch_job_id,
        organization_id=str(principal.organization_id),
        created_by_user_id=str(principal.user_id),
        document_id=document_id,
        source_filename=file.filename,
    )
    store.mark_stage(
        batch_job_id,
        "split",
        status="running",
        job_status="running",
        detail="Queued for background split",
    )

    process_bulk_payslip_pdf.delay(batch_job_id, document_id)

    return BatchJobResponse(batch_job_id=batch_job_id, status="queued")


@router.get("/jobs", response_model=list[BatchJobStatusResponse])
async def list_batch_jobs(
    principal: AuthPrincipal = Depends(require_accountant),
) -> list[BatchJobStatusResponse]:
    store = get_batch_progress_store()
    return [
        BatchJobStatusResponse(**job.to_dict())
        for job in store.list_recent(organization_id=str(principal.organization_id))
    ]


@router.get("/jobs/{batch_job_id}", response_model=BatchJobStatusResponse)
async def get_batch_job_status(
    batch_job_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchJobStatusResponse:
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None or job.organization_id != str(principal.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch job not found."},
        )
    return BatchJobStatusResponse(**job.to_dict())


@router.get("/jobs/{batch_job_id}/report", response_model=BatchReportResponse)
async def get_batch_report(
    batch_job_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchReportResponse:
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None or job.organization_id != str(principal.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch job not found."},
        )
    summary = job.report_summary
    if not summary:
        summary = {"total": 0, "passed": 0, "warnings": 0, "critical": 0}
    return BatchReportResponse(
        summary=summary,
        items=[
            BatchExtractedItemResponse(**item.to_dict()) for item in job.items
        ],
    )


@router.get(
    "/jobs/{batch_job_id}/items/{item_id}/review",
    response_model=BatchItemReviewResponse,
)
async def get_batch_item_review(
    batch_job_id: str,
    item_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchItemReviewResponse:
    """Load the exact persisted payslip workspace, including unmatched items."""
    _, item = _require_batch_item(batch_job_id, item_id, principal)
    if not item.document_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "batch_document_missing", "message": "Document is unavailable."},
        )
    document_id = UUID(item.document_id)
    document = await get_document_repository().get_by_id(document_id)
    if document is None or document.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    extraction = await get_document_extraction_repository().get_latest_for_document(document_id)
    explainability_enabled = bool(get_settings().layout_explainability_enabled)
    fields = (
        fields_for_workspace_api(review_fields_from_structured(extraction.structured_data))
        if extraction
        else []
    )
    entries = (
        [entry.to_dict() for entry in entries_from_structured(extraction.structured_data)]
        if extraction
        else []
    )
    evidence_by_field = (
        build_field_evidence_map(
            extraction.structured_data,
            extraction.layout_analysis,
        )
        if explainability_enabled and extraction
        else {}
    )
    if evidence_by_field:
        fields = attach_field_evidence(fields, evidence_by_field)
    runs = await get_validation_run_repository().list_for_document(document_id)
    findings_repo = get_validation_finding_repository()
    extraction_repo = get_document_extraction_repository()
    run_evidence_cache: dict[str, tuple[dict, dict]] = {}
    validation_history: list[dict] = []
    for run in runs:
        findings = await findings_repo.list_by_run_id(run.id)
        run_structured: dict = {}
        run_evidence: dict = {}
        if explainability_enabled:
            run_key = str(run.extraction_id) if run.extraction_id else ""
            if run_key and run_key in run_evidence_cache:
                run_structured, run_evidence = run_evidence_cache[run_key]
            elif run.extraction_id is not None:
                if extraction is not None and run.extraction_id == extraction.id:
                    run_ext = extraction
                else:
                    run_ext = await extraction_repo.get_by_id(run.extraction_id)
                if run_ext is not None:
                    run_structured = dict(run_ext.structured_data or {})
                    run_evidence = build_field_evidence_map(
                        run_ext.structured_data,
                        run_ext.layout_analysis,
                    )
                run_evidence_cache[run_key] = (run_structured, run_evidence)
        validation_history.append(
            {
                "validation_run_id": str(run.id),
                "status": run.status.value,
                "overall_result": (
                    run.overall_result.value if run.overall_result is not None else None
                ),
                "confidence": (
                    float(run.overall_confidence)
                    if run.overall_confidence is not None
                    else None
                ),
                "completed_at": (
                    run.completed_at.isoformat() if run.completed_at is not None else None
                ),
                "extraction_id": str(run.extraction_id) if run.extraction_id else None,
                "outdated": bool(
                    extraction is not None
                    and run.extraction_id is not None
                    and run.extraction_id != extraction.id
                ),
                "findings": [
                    {
                        "id": str(finding.id),
                        "rule_id": finding.rule_id,
                        "category": finding.rule_category.value,
                        "severity": finding.severity.value,
                        "message_key": finding.message_key,
                        "message_params": dict(finding.message_params or {}),
                        "expected_value": finding.expected_value,
                        "actual_value": finding.actual_value,
                        "confidence": float(finding.confidence),
                        **(
                            {
                                "evidence_explanation": build_validation_explanation(
                                    finding=finding,
                                    structured_data=run_structured,
                                    evidence_by_field=run_evidence,
                                )
                            }
                            if explainability_enabled
                            else {}
                        ),
                    }
                    for finding in findings
                ],
                **(
                    {
                        "evidence_summary": build_validation_run_explanation(
                            overall_result=run.overall_result,
                            fields=fields_for_workspace_api(
                                fields_from_structured(run_structured)
                            )
                            if run_structured
                            else [],
                            evidence_by_field=run_evidence,
                        )
                    }
                    if explainability_enabled
                    else {}
                ),
            }
        )
    return BatchItemReviewResponse(
        item=BatchExtractedItemResponse(**item.to_dict()),
        document_id=str(document.id),
        original_filename=document.original_filename,
        uploaded_at=document.created_at.isoformat() if document.created_at else None,
        fields=fields,
        entries=entries,
        extraction_id=str(extraction.id) if extraction else None,
        extraction_version=extraction.extraction_version if extraction else None,
        validation_history=validation_history,
        explainability_enabled=explainability_enabled,
    )


@router.get("/jobs/{batch_job_id}/items/{item_id}/content")
async def get_batch_item_content(
    batch_job_id: str,
    item_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> Response:
    """Stream the exact split source document to the accountant reviewer."""
    _, item = _require_batch_item(batch_job_id, item_id, principal)
    if not item.document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document = await get_document_repository().get_by_id(UUID(item.document_id))
    if document is None or document.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    payload = await create_object_storage(get_settings()).download(document.storage_key)
    return Response(
        content=payload,
        media_type=document.mime_type or "application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{document.original_filename.replace(chr(34), "")}"'
            )
        },
    )


@router.put(
    "/jobs/{batch_job_id}/items/{item_id}/review",
    response_model=BatchItemReviewResponse,
)
async def correct_batch_item_review(
    batch_job_id: str,
    item_id: str,
    request: BatchReviewCorrectionRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchItemReviewResponse:
    """Persist structured corrections as a new extraction version without OCR."""
    _, item = _require_batch_item(batch_job_id, item_id, principal)
    if not item.document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document = await get_document_repository().get_by_id(UUID(item.document_id))
    if document is None or document.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await CorrectGuestExtractionUseCase(
        document_repository=get_document_repository(),
        extraction_repository=get_document_extraction_repository(),
    ).execute(
        document_id=document.id,
        corrections=[
            FieldCorrection(key=row.key, value=row.value, clear=row.clear)
            for row in request.corrections
        ],
    )
    return await get_batch_item_review(batch_job_id, item_id, principal)


@router.post(
    "/jobs/{batch_job_id}/items/{item_id}/validate",
    response_model=BatchItemReviewResponse,
)
async def validate_batch_item_review(
    batch_job_id: str,
    item_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
    validation: RunPersistedValidationUseCase = Depends(
        get_run_persisted_validation_use_case
    ),
) -> BatchItemReviewResponse:
    """Create a new validation run for this payslip only."""
    _, item = _require_batch_item(batch_job_id, item_id, principal)
    if not item.document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document = await get_document_repository().get_by_id(UUID(item.document_id))
    if document is None or document.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await validation.execute(
        RunPersistedValidationCommand(
            document_id=document.id,
            employee_id=document.employee_id,
            include_historical=True,
            include_contract_rag=document.employee_id is not None,
        )
    )
    return await get_batch_item_review(batch_job_id, item_id, principal)


@router.post(
    "/jobs/{batch_job_id}/items/{item_id}/resolve",
    response_model=BatchExtractedItemResponse,
)
async def resolve_batch_item(
    batch_job_id: str,
    item_id: str,
    request: BatchItemResolutionRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchExtractedItemResponse:
    """Resolve an unknown batch item within the accountant's organization only."""
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None or job.organization_id != str(principal.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch job not found."},
        )
    item = next((row for row in job.items if row.id == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_item_not_found", "message": "Batch item not found."},
        )
    if request.action == "ignore":
        if item.document_id:
            parsed_document_id = UUID(item.document_id)
            document = await get_document_repository().get_by_id(parsed_document_id)
            if document is not None and document.organization_id == principal.organization_id:
                runs = await get_validation_run_repository().list_for_document(
                    parsed_document_id
                )
                run_ids = [run.id for run in runs]
                if run_ids:
                    await get_validation_finding_repository().delete_for_run_ids(
                        run_ids
                    )
                await get_validation_run_repository().delete_for_document_ids(
                    [parsed_document_id]
                )
                await get_document_extraction_repository().delete_for_document_ids(
                    [parsed_document_id]
                )
                from payroll_copilot.infrastructure.storage.factory import (
                    create_object_storage,
                )

                await create_object_storage(get_settings()).delete(document.storage_key)
                await get_document_repository().delete_by_ids([parsed_document_id])
        updated = replace(
            item,
            status="failed",
            processing_stage="completed",
            review_status="ignored",
            resolution_status="ignored",
            error_message="Ignored by payroll accountant.",
            document_id=None,
            validation_run_id=None,
        )
    else:
        if not item.document_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "batch_document_missing",
                    "message": "The extracted payslip document is unavailable.",
                },
            )
        organization_id = UUID(str(principal.organization_id))
        pipeline = create_batch_payslip_pipeline()
        if request.action == "edit_national_id":
            if not request.national_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "national_id_required", "message": "National ID is required."},
                )
            correction = CorrectGuestExtractionUseCase(
                document_repository=get_document_repository(),
                extraction_repository=get_document_extraction_repository(),
            )
            await correction.execute(
                document_id=UUID(item.document_id),
                corrections=[
                    FieldCorrection(
                        key="employee_id",
                        value=request.national_id,
                    )
                ],
            )
            employee = await pipeline.find_employee_by_national_id(
                organization_id,
                request.national_id,
            )
        else:
            if not request.employee_number:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "employee_number_required",
                        "message": "Employee number is required.",
                    },
                )
            employee = await pipeline.find_employee_by_number(
                organization_id,
                request.employee_number,
            )
        if employee is None:
            updated = replace(
                item,
                status="unknown_employee",
                resolution_status="not_matched",
                error_message="No employee matched inside this organization.",
            )
        else:
            try:
                result = await pipeline.finalize_document(
                    document_id=UUID(item.document_id),
                    employee=employee,
                    actor_user_id=principal.user_id,
                )
                updated = BatchExtractedItem(
                    id=item.id,
                    slip_index=item.slip_index,
                    status=result.status,
                    employee_number=result.employee_number,
                    employee_name=result.employee_name,
                    document_id=str(result.document_id),
                    national_id_masked=result.national_id_masked,
                    payroll_year=result.payroll_year,
                    payroll_month=result.payroll_month,
                    warnings=result.warnings,
                    critical_issues=result.critical_issues,
                    processing_stage=result.processing_stage,
                    validation_run_id=(
                        str(result.validation_run_id)
                        if result.validation_run_id
                        else None
                    ),
                    error_message=result.error_message,
                    resolution_status="attached",
                )
            except Exception as exc:  # noqa: BLE001 - resolution result is persisted
                updated = replace(
                    item,
                    status="failed",
                    employee_number=employee.employee_number,
                    employee_name=employee.full_name,
                    processing_stage="validation",
                    resolution_status="attachment_failed",
                    error_message=str(exc) or exc.__class__.__name__,
                )
    store.upsert_item(batch_job_id, updated)
    refreshed = store.get(batch_job_id)
    if refreshed is not None:
        summary = {
            "total": len(refreshed.items),
            "passed": sum(row.status == "passed" for row in refreshed.items),
            "warnings": sum(row.status == "warning" for row in refreshed.items),
            "failed": sum(row.status == "failed" for row in refreshed.items),
            "unknown": sum(
                row.status == "unknown_employee" for row in refreshed.items
            ),
            "processing": sum(
                row.status == "processing" for row in refreshed.items
            ),
        }
        store.mark_stage(
            batch_job_id,
            "report",
            status="completed",
            report_summary=summary,
            failed_slips=summary["failed"],
        )
    return BatchExtractedItemResponse(**updated.to_dict())


@router.post(
    "/jobs/{batch_job_id}/items/{item_id}/publish",
    response_model=BatchPublishResponse,
)
async def publish_batch_item(
    batch_job_id: str,
    item_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> BatchPublishResponse:
    """Final approval boundary: only here does a draft become employee-visible."""
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None or job.organization_id != str(principal.organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_not_found", "message": "Batch job not found."},
        )
    item = next((row for row in job.items if row.id == item_id), None)
    if item is None or not item.document_id or not item.employee_number:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "batch_item_not_publishable",
                "message": "Link this payslip to an employee before publishing.",
            },
        )
    selected = await bind_accountant_selected_employee(
        employee_number=item.employee_number,
        principal=principal,
    )
    use_case = PublishBatchPayslipUseCase(
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
        validation_runs=get_validation_run_repository(),
        audit_logs=get_audit_log_repository(),
    )
    try:
        result = await use_case.execute(
            document_id=UUID(item.document_id),
            employee=selected.employee,
            actor_user_id=principal.user_id,
        )
    except (DocumentNotFoundError, DocumentNotOwnedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "batch_document_not_found", "message": str(exc)},
        ) from exc
    except ConfirmationBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    store.upsert_item(
        batch_job_id,
        replace(
            item,
            review_status="approved",
            publication_status="published",
            resolution_status="published",
            validation_run_id=str(result.validation_run_id),
            error_message=None,
        ),
    )
    return BatchPublishResponse(
        document_id=str(result.document_id),
        employee_number=result.employee_number,
        payroll_year=result.payroll_year,
        payroll_month=result.payroll_month,
        published_at=result.published_at,
        validation_run_id=str(result.validation_run_id),
    )
