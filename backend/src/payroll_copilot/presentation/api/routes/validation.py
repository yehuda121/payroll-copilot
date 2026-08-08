"""Validation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
    get_workspace_bootstrap,
)

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
    ExtractionNotConfirmedError,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    GetValidationRunUseCase,
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
)
from payroll_copilot.application.services.guest_ephemeral_store import (
    get_guest_ephemeral_store,
    guest_owns_ephemeral,
)
from payroll_copilot.application.use_cases.validate_employee_payslip import ValidateEmployeePayslipUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    ExtractionRequiredError,
)
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.ai.agents.validation_report_store import cache_validation_report
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.i18n import finding_explanation, finding_message, resolve_locale
from payroll_copilot.presentation.api.dependencies import (
    get_run_persisted_validation_use_case,
    get_validation_run_use_case,
)
from payroll_copilot.presentation.api.rate_limit_deps import (
    limit_validation_by_user,
    limit_validation_guest_by_guest,
    limit_validation_guest_by_ip,
)
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    GuestPrincipal,
    bind_accountant_selected_employee,
    get_auth_principal,
    require_accountant,
    require_bound_employee,
    require_guest,
)

router = APIRouter()

class ValidationRunRequest(BaseModel):
    document_id: str
    employee_id: str | None = None
    include_historical: bool = True
    include_contract_rag: bool = True
    supporting_document_ids: list[str] = Field(default_factory=list)
    locale: str | None = Field(default=None, pattern="^(he|en|ar)$")
    rerun_scope: str | None = None
    rule_ids: list[str] = Field(default_factory=list)


class ManualApprovalRequest(BaseModel):
    document_id: str
    validation_run_id: str
    finding_id: str | None = None
    rule_id: str | None = None
    acknowledgement: bool = False
    reason: str | None = None
    locale: str | None = Field(default=None, pattern="^(he|en|ar)$")

class ValidationScopeItemResponse(BaseModel):
    key: str
    label: str
    status: str
    reason: str | None = None

class UploadedDocumentResponse(BaseModel):
    document_type: str
    document_id: str
    uploaded: bool
    original_filename: str | None = None

class FindingResponse(BaseModel):
    id: str
    code: str
    rule_id: str
    severity: str
    message_key: str
    message: str
    explanation: str
    expected_value: str | None
    actual_value: str | None
    confidence: float
    legal_reference: str | None = None
    display_status: str | None = None
    manual_approval: dict | None = None


class RuleOutcomeResponse(BaseModel):
    rule_id: str
    outcome: str
    skip_reason: str | None = None
    reason_code: str | None = None
    message: str | None = None
    category: str | None = None
    display_category: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    legal_source: str | None = None
    legal_version: str | None = None


class ValidationRunResponse(BaseModel):
    id: str
    document_id: str
    status: str
    locale: str
    overall_result: str | None = None
    overall_confidence: float | None = None
    rules_evaluated: int = 0
    rules_failed: int = 0
    checks_passed_count: int = 0
    validation_confidence: float | None = None
    confidence_explanation: str | None = None
    validation_scope: list[ValidationScopeItemResponse] = Field(default_factory=list)
    uploaded_documents: list[UploadedDocumentResponse] = Field(default_factory=list)
    extraction_connected: bool = False
    findings: list[FindingResponse] = Field(default_factory=list)
    rule_outcomes: list[RuleOutcomeResponse] = Field(default_factory=list)
    manual_approvals: list[dict] = Field(default_factory=list)
    legal_rules_version: str | None = None
    legal_rules_effective_from: str | None = None

def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: must be a valid UUID",
        ) from exc


def _normalize_outcome(outcome: str) -> str:
    """Map legacy skipped → not_run for API consumers."""
    if outcome == "skipped":
        return "not_run"
    return outcome


def _to_response(record: ValidationRunRecord, *, locale: str, document_metadata: dict | None = None) -> ValidationRunResponse:
    from payroll_copilot.application.use_cases.approve_validation_finding import (
        apply_approvals_to_display,
        approvals_from_document_metadata,
    )

    enrichment = record.enrichment
    validation_scope: list[ValidationScopeItemResponse] = []
    uploaded_documents: list[UploadedDocumentResponse] = []
    validation_confidence: float | None = None
    confidence_explanation: str | None = None
    checks_passed_count = max(record.rules_evaluated - record.rules_failed, 0)
    extraction_connected = False

    if enrichment is not None:
        validation_scope = [
            ValidationScopeItemResponse(
                key=item.key,
                label=item.label,
                status=item.status,
                reason=item.reason,
            )
            for item in enrichment.validation_scope
        ]
        uploaded_documents = [
            UploadedDocumentResponse(
                document_type=item.document_type,
                document_id=item.document_id,
                uploaded=item.uploaded,
                original_filename=item.original_filename,
            )
            for item in enrichment.uploaded_documents
        ]
        validation_confidence = float(enrichment.validation_confidence)
        confidence_explanation = enrichment.confidence_explanation
        checks_passed_count = enrichment.checks_passed_count
        extraction_connected = enrichment.extraction_connected

    finding_payloads = [
        {
            "id": str(finding.id),
            "code": finding.message_key,
            "rule_id": finding.rule_id,
            "severity": finding.severity.value,
            "message_key": finding.message_key,
            "message": finding_message(finding.message_key, locale),
            "explanation": finding_explanation(finding.message_key, locale),
            "expected_value": finding.expected_value,
            "actual_value": finding.actual_value,
            "confidence": float(finding.confidence),
            "legal_reference": finding.legal_reference,
        }
        for finding in record.findings
    ]
    annotated = apply_approvals_to_display(
        findings=finding_payloads,
        approvals=approvals_from_document_metadata(document_metadata),
    )

    rule_outcomes = [
        RuleOutcomeResponse(
            rule_id=str(item.get("rule_id") or ""),
            outcome=_normalize_outcome(str(item.get("outcome") or "not_run")),
            skip_reason=item.get("skip_reason"),
            reason_code=item.get("reason_code"),
            message=item.get("message"),
            category=item.get("category"),
            display_category=item.get("display_category"),
            required_inputs=[
                str(x) for x in (item.get("required_inputs") or []) if x is not None
            ],
            legal_source=item.get("legal_source"),
            legal_version=item.get("legal_version"),
        )
        for item in (record.context_snapshot or {}).get("rule_outcomes") or []
        if isinstance(item, dict) and item.get("rule_id")
    ]

    snapshot = record.context_snapshot or {}
    response = ValidationRunResponse(
        id=str(record.id),
        document_id=str(record.document_id),
        status=record.status.value,
        locale=locale,
        overall_result=record.overall_result.value if record.overall_result else None,
        overall_confidence=float(record.overall_confidence) if record.overall_confidence else None,
        rules_evaluated=record.rules_evaluated,
        rules_failed=record.rules_failed,
        checks_passed_count=checks_passed_count,
        validation_confidence=validation_confidence,
        confidence_explanation=confidence_explanation,
        validation_scope=validation_scope,
        uploaded_documents=uploaded_documents,
        extraction_connected=extraction_connected,
        findings=[FindingResponse(**row) for row in annotated],
        rule_outcomes=rule_outcomes,
        manual_approvals=approvals_from_document_metadata(document_metadata),
        legal_rules_version=snapshot.get("legal_rules_version"),
        legal_rules_effective_from=snapshot.get("legal_rules_effective_from"),
    )

    return response

@router.post("/run", response_model=ValidationRunResponse, status_code=202)
async def run_validation(
    request: ValidationRunRequest,
    _: None = Depends(limit_validation_guest_by_ip),
    __: None = Depends(limit_validation_guest_by_guest),
    guest: GuestPrincipal = Depends(require_guest),
    use_case: RunPersistedValidationUseCase = Depends(get_run_persisted_validation_use_case),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    """Guest landing validation for ephemeral payslips only.

    Persisted employee/accountant documents must use the authenticated
    `/validation/employee/run` or `/validation/accountant/{employee_number}/run`
    endpoints.
    """
    settings = get_settings()
    locale = resolve_locale(
        explicit=request.locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    document_id = _parse_uuid(request.document_id, "document_id")
    store = get_guest_ephemeral_store()
    ephemeral = store.get(document_id)
    if ephemeral is None or not guest_owns_ephemeral(ephemeral, guest.guest_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "guest_session_not_found",
                "message": "Guest validation session not found for this document.",
            },
        )
    supporting_document_ids = tuple(
        _parse_uuid(value, "supporting_document_id") for value in request.supporting_document_ids
    )
    for support_id in supporting_document_ids:
        support = store.get_supporting(support_id)
        if support is None or not guest_owns_ephemeral(support, guest.guest_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "supporting_document_not_found",
                    "message": "Supporting document is not part of this guest session.",
                },
            )

    try:
        record = await use_case.execute(
            RunPersistedValidationCommand(
                document_id=document_id,
                employee_id=None,
                include_historical=False,
                include_contract_rag=False,
                supporting_document_ids=supporting_document_ids,
                locale=locale,
            )
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {exc.document_id} not found",
        ) from exc
    except ExtractionRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "extraction_required", "message": exc.message},
        ) from exc
    response = _to_response(record, locale=locale)
    cache_validation_report(
        response.id,
        {
            "status": response.status,
            "overall_result": response.overall_result,
            "findings": [finding.model_dump() for finding in response.findings],
        },
        owner_guest_id=guest.guest_id,
    )
    return response

@router.post("/employee/run", response_model=ValidationRunResponse, status_code=202)
async def run_employee_validation(
    request: ValidationRunRequest,
    _: None = Depends(limit_validation_by_user),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    validation: RunPersistedValidationUseCase = Depends(get_run_persisted_validation_use_case),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    """Validate an employee-owned payslip after trusted identity/period checks pass."""
    settings = get_settings()
    locale = resolve_locale(
        explicit=request.locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    document_id = _parse_uuid(request.document_id, "document_id")
    if bound.principal.role == "employee":
        document = await get_document_repository().get_by_id(document_id)
        if document is None or not is_employee_visible_document(document):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "document_not_found", "message": "Document not found"},
            )
    supporting_document_ids = tuple(
        _parse_uuid(value, "supporting_document_id") for value in request.supporting_document_ids
    )
    use_case = ValidateEmployeePayslipUseCase(
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
        validation=validation,
        audit_logs=get_audit_log_repository(),
    )
    try:
        result = await use_case.execute(
            document_id=document_id,
            employee=bound.employee,
            user_id=bound.principal.user_id,
            national_id_encrypted=bound.national_id_encrypted,
            supporting_document_ids=supporting_document_ids,
            locale=locale,
            rerun_scope=request.rerun_scope,
            rule_ids=tuple(request.rule_ids),
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"Document {exc.document_id} not found"},
        ) from exc
    except DocumentNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Document is not owned by the authenticated employee."},
        ) from exc
    except ConfirmationBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ExtractionNotConfirmedError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc
    except ExtractionRequiredError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "extraction_required", "message": tip_exc.message},
        ) from tip_exc
    doc_for_meta = await get_document_repository().get_by_id(document_id)
    return _to_response(
        result.record,
        locale=locale,
        document_metadata=dict(doc_for_meta.metadata or {}) if doc_for_meta is not None else None,
    )


@router.post(
    "/accountant/{employee_number}/run",
    response_model=ValidationRunResponse,
    status_code=202,
)
async def run_accountant_selected_employee_validation(
    employee_number: str,
    request: ValidationRunRequest,
    _: None = Depends(limit_validation_by_user),
    principal: AuthPrincipal = Depends(require_accountant),
    validation: RunPersistedValidationUseCase = Depends(
        get_run_persisted_validation_use_case
    ),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    return await run_employee_validation(
        request=request,
        bound=selected,
        validation=validation,
        accept_language=accept_language,
    )


@router.get("/runs/{validation_run_id}", response_model=ValidationRunResponse)
async def get_validation_run(
    validation_run_id: str,
    use_case: GetValidationRunUseCase = Depends(get_validation_run_use_case),
    principal: AuthPrincipal = Depends(get_auth_principal),
    locale: str | None = None,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    settings = get_settings()
    resolved = resolve_locale(
        explicit=locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    run_id = _parse_uuid(validation_run_id, "validation_run_id")
    record = await use_case.execute(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation run {validation_run_id} not found",
        )
    await _authorize_validation_run_access(record=record, principal=principal)
    document = await get_document_repository().get_by_id(record.document_id)
    return _to_response(
        record,
        locale=resolved,
        document_metadata=dict(document.metadata or {}) if document else None,
    )


@router.post("/employee/findings/approve", status_code=200)
async def approve_employee_finding(
    request: ManualApprovalRequest,
    _: None = Depends(limit_validation_by_user),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict:
    """Manually approve a failed/uncertain finding without destroying the original verdict."""
    from payroll_copilot.application.use_cases.approve_validation_finding import (
        ApproveValidationFindingUseCase,
        ManualApprovalError,
    )

    if not request.finding_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "finding_id_required", "message": "finding_id is required."},
        )

    use_case = ApproveValidationFindingUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        audit_logs=get_audit_log_repository(),
    )
    try:
        result = await use_case.execute(
            document_id=_parse_uuid(request.document_id, "document_id"),
            validation_run_id=_parse_uuid(request.validation_run_id, "validation_run_id"),
            finding_id=_parse_uuid(request.finding_id, "finding_id"),
            employee=bound.employee,
            actor_user_id=bound.principal.user_id,
            actor_role=bound.principal.role,
            acknowledgement=request.acknowledgement,
            reason=request.reason,
        )
    except ManualApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotOwnedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return result


@router.post("/accountant/{employee_number}/checks/approve", status_code=200)
async def approve_accountant_check(
    employee_number: str,
    request: ManualApprovalRequest,
    _: None = Depends(limit_validation_by_user),
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict:
    """Accountant check-level manual approval. Does not rewrite deterministic outcomes."""
    from payroll_copilot.application.use_cases.approve_validation_finding import (
        ApproveValidationFindingUseCase,
        ManualApprovalError,
    )

    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    use_case = ApproveValidationFindingUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        audit_logs=get_audit_log_repository(),
    )
    rule_id = (request.rule_id or "").strip()
    if not rule_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "rule_id_required", "message": "rule_id is required."},
        )
    try:
        result = await use_case.execute_check(
            document_id=_parse_uuid(request.document_id, "document_id"),
            validation_run_id=_parse_uuid(request.validation_run_id, "validation_run_id"),
            rule_id=rule_id,
            finding_id=(
                _parse_uuid(request.finding_id, "finding_id") if request.finding_id else None
            ),
            organization_id=selected.employee.organization_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role,
            acknowledgement=request.acknowledgement,
            reason=request.reason,
        )
    except ManualApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotOwnedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return result


@router.post("/accountant/documents/{document_id}/checks/approve", status_code=200)
async def approve_accountant_document_check(
    document_id: str,
    request: ManualApprovalRequest,
    _: None = Depends(limit_validation_by_user),
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict:
    """Org-scoped check approval for batch review (document may lack employee bind)."""
    from payroll_copilot.application.use_cases.approve_validation_finding import (
        ApproveValidationFindingUseCase,
        ManualApprovalError,
    )

    if principal.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="organization_required")
    use_case = ApproveValidationFindingUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        audit_logs=get_audit_log_repository(),
    )
    rule_id = (request.rule_id or "").strip()
    if not rule_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "rule_id_required", "message": "rule_id is required."},
        )
    try:
        result = await use_case.execute_check(
            document_id=_parse_uuid(document_id, "document_id"),
            validation_run_id=_parse_uuid(request.validation_run_id, "validation_run_id"),
            rule_id=rule_id,
            finding_id=(
                _parse_uuid(request.finding_id, "finding_id") if request.finding_id else None
            ),
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role,
            acknowledgement=request.acknowledgement,
            reason=request.reason,
        )
    except ManualApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentNotOwnedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return result


async def _authorize_validation_run_access(
    *,
    record: ValidationRunRecord,
    principal: AuthPrincipal,
) -> None:
    """Hide cross-tenant validation runs behind a generic not-found response."""
    document = await get_document_repository().get_by_id(record.document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation run {record.id} not found",
        )

    if principal.role == UserRole.EMPLOYEE.value:
        if (
            principal.employee_id is None
            or document.employee_id != principal.employee_id
            or document.organization_id != principal.organization_id
            or not is_employee_visible_document(document)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Validation run {record.id} not found",
            )
        return

    if principal.role in {UserRole.ACCOUNTANT.value, UserRole.ADMIN.value}:
        if (
            principal.organization_id is None
            or document.organization_id != principal.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Validation run {record.id} not found",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "validation_access_denied",
            "message": "Authenticated role cannot access validation runs.",
        },
    )
