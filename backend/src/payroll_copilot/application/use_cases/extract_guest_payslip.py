"""Guest/Employee/Batch payslip extraction (deterministic PDF text → Document Model).

Stage-1: shared ``extract_document_from_pdf`` (PyMuPDF text layer + regex parsers).
No OpenAI / LLM / OCR / agent participates in extraction.

Stage-2 canonical mapping runs for durable paths so validation/matching work;
Document Model is always preserved under structured_data.dynamic_entries.

Does not run Rule Engine / deterministic validation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.exceptions import ExtractionCancelledError
from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.deterministic_pdf import (
    DeterministicExtractionStatus,
    DeterministicPdfDocumentExtractor,
    EXTRACTOR_VERSION,
    fields_to_dynamic_entries,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_have_usable_values,
    is_document_origin_entry,
    project_structured_from_entries,
    review_rows_from_structured,
)

from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    get_guest_ephemeral_store,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID
from payroll_copilot.infrastructure.ocr.extraction_timing import ExtractionTimer

CancelCheck = Callable[[], bool] | None
ProgressCallback = Callable[[str, dict[str, Any] | None], None] | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class ExtractedFieldView:
    key: str
    value: Any
    confidence: float | None
    source_text: str | None
    status: str
    edited_by_user: bool = False
    original_value: Any = None


@dataclass(frozen=True, slots=True)
class GuestPayslipExtractionResult:
    document_id: UUID
    extraction_id: UUID
    ocr_status: str
    parser_status: str
    language: str
    ocr_engine: str | None
    parser_model: str | None
    warnings: list[str]
    fields: list[ExtractedFieldView]
    raw_text: str
    error_message: str | None = None
    entries: list[DynamicDocumentEntry] | None = None


@dataclass(frozen=True, slots=True)
class GuestPayslipExtractionCommand:
    content: bytes
    original_filename: str
    mime_type: str
    language: str = "auto"
    employee_id: UUID | None = None
    organization_id: UUID | None = None
    uploaded_by: UUID | None = None
    period_year: int | None = None
    period_month: int | None = None
    confirm_new_version: bool = False
    metadata_extra: dict[str, Any] | None = None
    ephemeral: bool = True
    cancel_check: CancelCheck = None
    reuse_document_id: UUID | None = None
    progress_callback: ProgressCallback = None
    owner_guest_id: str | None = None
    model_provider_override: str | None = None


class ExtractGuestPayslipUseCase:
    """Upload payslip bytes, run shared deterministic Document Model extraction, persist results."""

    def __init__(
        self,
        *,
        document_repository: DocumentRepository,
        extraction_repository: DocumentExtractionRepository,
        object_storage: ObjectStoragePort,
        organization_bootstrap: OrganizationBootstrapPort,
        deterministic_extractor: DeterministicPdfDocumentExtractor | None = None,
    ) -> None:
        self._documents = document_repository
        self._extractions = extraction_repository
        self._storage = object_storage
        self._org_bootstrap = organization_bootstrap
        self._deterministic = deterministic_extractor or DeterministicPdfDocumentExtractor()

    async def execute(self, command: GuestPayslipExtractionCommand) -> GuestPayslipExtractionResult:
        timer = ExtractionTimer(document_type="payslip")
        self._check_cancelled(command.cancel_check)
        timer.log_stage("upload_validation")

        use_ephemeral = command.ephemeral and command.employee_id is None
        if command.reuse_document_id is not None:
            document_id = command.reuse_document_id
            extraction_id = uuid4()
        else:
            document_id, extraction_id = (
                get_guest_ephemeral_store().new_ids() if use_ephemeral else (uuid4(), uuid4())
            )

        warnings: list[str] = []
        ocr_status = "pending"
        parser_status = "pending"
        ocr_engine: str | None = None
        parser_model: str | None = None
        raw_text = ""
        ocr_payload: dict[str, Any] = {}
        layout_snapshot: dict[str, Any] = {}
        layout_analysis: dict[str, Any] = {}
        structured: dict[str, Any] = {}
        field_confidences: dict[str, float] = {}
        fields: list[ExtractedFieldView] = []
        dynamic_entries: list[DynamicDocumentEntry] = []
        error_message: str | None = None
        language = command.language
        document: Document | None = None

        if not use_ephemeral:
            if command.reuse_document_id is not None:
                document = await self._documents.get_by_id(command.reuse_document_id)
                if document is None:
                    raise ValueError(f"Document not found: {command.reuse_document_id}")
                meta = dict(document.metadata or {})
                meta["lifecycle_status"] = "processing"
                if command.metadata_extra:
                    meta.update(command.metadata_extra)
                document.metadata = meta
                document.status = DocumentStatus.PROCESSING
                await self._documents.save(document)
            else:
                document = await self._persist_document(command, document_id=document_id)

        try:
            self._check_cancelled(command.cancel_check)
            self._notify_progress(command.progress_callback, "extracting")
            result = self._deterministic.extract(
                command.content,
                document_type=DocumentType.PAYSLIP,
                filename=command.original_filename,
                mime_type=command.mime_type,
            )
            timer.log_stage(
                "deterministic_pdf_text",
                page_count=result.page_count,
                extracted_text_length=len(result.raw_text or ""),
            )
            raw_text = result.raw_text
            ocr_engine = result.engine
            parser_model = result.extractor_version
            warnings.extend(list(result.warnings))
            ocr_payload = {
                "engine": result.engine,
                "language_requested": command.language,
                "language_effective": language,
                "overall_confidence": None,
                "raw_text": raw_text,
                "warnings": list(result.warnings),
                "pages": [
                    {
                        "page": index,
                        "language": language,
                        "text": page_text,
                        "confidence": None,
                        "lines": [],
                        "words": [],
                    }
                    for index, page_text in enumerate(result.page_texts, start=1)
                ],
                "deterministic_status": result.status.value,
                "error_code": result.error_code,
            }

            if result.status is DeterministicExtractionStatus.OCR_REQUIRED:
                ocr_status = "ocr_required"
                parser_status = "skipped"
                error_message = result.error_message
                warnings.append(result.error_code or "OCR_REQUIRED")
            elif result.status is DeterministicExtractionStatus.REJECTED:
                ocr_status = "failed"
                parser_status = "skipped"
                error_message = result.error_message
                if result.error_code:
                    warnings.append(result.error_code)
            elif result.status is DeterministicExtractionStatus.FAILED:
                ocr_status = "completed"
                parser_status = "failed"
                error_message = result.error_message
                if result.error_code:
                    warnings.append(result.error_code)
                structured = dict(result.structured or {})
            else:
                ocr_status = "completed"
                dynamic_entries = fields_to_dynamic_entries(result.fields)
                extractor_meta = dict((result.structured or {}).get("extractor_meta") or {})
                extractor_meta.setdefault("extractor_version", EXTRACTOR_VERSION)
                if not entries_have_usable_values(dynamic_entries):
                    parser_status = "failed"
                    error_message = "We could not extract usable information from this document."
                    warnings.append("deterministic_extractor_no_usable_entries")
                    structured = {
                        "dynamic_entries": [e.to_dict() for e in dynamic_entries],
                        "extractor_meta": extractor_meta,
                    }
                else:
                    parser_status = "completed"
                    review_fields = _fields_from_entries(dynamic_entries)
                    if use_ephemeral:
                        structured = {
                            "dynamic_entries": [e.to_dict() for e in dynamic_entries],
                            "extractor_meta": extractor_meta,
                        }
                        fields = review_fields
                        field_confidences = {
                            entry.key: entry.confidence
                            for entry in dynamic_entries
                            if entry.confidence is not None and entry.key
                        }
                    else:
                        structured, map_warnings = project_structured_from_entries(dynamic_entries)
                        structured["extractor_meta"] = extractor_meta
                        warnings.extend(map_warnings)
                        fields, field_confidences = _fields_from_structured(structured)
                    timer.log_stage(
                        "document_reconstruction",
                        page_count=result.page_count,
                        extracted_text_length=len(raw_text),
                        extracted_field_count=len(
                            [e for e in dynamic_entries if is_document_origin_entry(e)]
                        ),
                        extractor_version=extractor_meta.get("extractor_version"),
                    )
        except ExtractionCancelledError:
            timer.log_stage("extraction_cancelled", error_code="extraction_cancelled")
            raise

        if use_ephemeral:
            session = GuestEphemeralSession(
                document_id=document_id,
                extraction_id=extraction_id,
                content=command.content,
                original_filename=command.original_filename,
                mime_type=command.mime_type,
                language=language,
                ocr_status=ocr_status,
                parser_status=parser_status,
                ocr_engine=ocr_engine,
                parser_model=parser_model,
                raw_text=raw_text,
                structured_data=structured,
                ocr_result=ocr_payload,
                warnings=list(dict.fromkeys(warnings)),
                error_message=error_message,
                field_confidences=field_confidences,
                dynamic_entries=[e.to_dict() for e in dynamic_entries],
                owner_guest_id=command.owner_guest_id,
            )
            get_guest_ephemeral_store().save(session)
            timer.log_summary()
            return GuestPayslipExtractionResult(
                document_id=document_id,
                extraction_id=extraction_id,
                ocr_status=ocr_status,
                parser_status=parser_status,
                language=language,
                ocr_engine=ocr_engine,
                parser_model=parser_model,
                warnings=list(dict.fromkeys(warnings)),
                fields=fields,
                raw_text=raw_text,
                error_message=error_message,
                entries=dynamic_entries,
            )

        assert document is not None
        now = _utcnow()
        version = 1
        latest = await self._extractions.get_latest_for_document(document.id)
        if latest is not None:
            version = int(latest.extraction_version or 1) + 1
        extraction = DocumentExtraction(
            id=extraction_id,
            document_id=document.id,
            engine=ocr_engine or EXTRACTOR_VERSION,
            raw_text=raw_text,
            structured_data=structured,
            overall_confidence=None,
            field_confidences=field_confidences,
            extraction_version=version,
            created_at=now,
            ocr_result=ocr_payload,
            layout_snapshot=layout_snapshot,
            layout_analysis=layout_analysis,
            parser_model=parser_model,
            language=language,
            ocr_status=ocr_status,
            parser_status=parser_status,
            warnings=list(dict.fromkeys(warnings)),
            error_message=error_message,
            updated_at=now,
            confirmation_status="review_required",
        )
        await self._extractions.save(extraction)
        document.metadata = {
            **(document.metadata or {}),
            "current_extraction_id": str(extraction.id),
            "current_extraction_version": version,
        }
        await self._documents.save(document)
        timer.log_stage("persistence")
        timer.log_summary()

        if not fields and structured:
            fields, _ = _fields_from_structured(structured)

        return GuestPayslipExtractionResult(
            document_id=document.id,
            extraction_id=extraction_id,
            ocr_status=ocr_status,
            parser_status=parser_status,
            language=language,
            ocr_engine=ocr_engine,
            parser_model=parser_model,
            warnings=list(dict.fromkeys(warnings)),
            fields=fields,
            raw_text=raw_text,
            error_message=error_message,
            entries=dynamic_entries,
        )

    def confirm_ephemeral_session(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any] | None = None,
        dynamic_entries: list[dict[str, Any]] | None = None,
    ) -> tuple[Document, DocumentExtraction]:
        store = get_guest_ephemeral_store()
        session = store.get(document_id)
        if session is None:
            raise ValueError(f"Guest ephemeral session not found: {document_id}")

        entries_payload = dynamic_entries if dynamic_entries is not None else session.dynamic_entries
        entries = [
            DynamicDocumentEntry.from_dict(item)
            for item in entries_payload
            if isinstance(item, dict)
        ]
        mapped, map_warnings = project_structured_from_entries(entries)
        if structured_data is not None:
            mapped = dict(structured_data)
            mapped["dynamic_entries"] = [e.to_dict() for e in entries]
        if map_warnings:
            session.warnings = list(dict.fromkeys([*session.warnings, *map_warnings]))

        confirmed = store.confirm(
            document_id,
            structured_data=mapped,
            dynamic_entries=[e.to_dict() for e in entries],
        )
        if confirmed is None:
            raise ValueError(f"Guest ephemeral session not found: {document_id}")
        return store.build_document(confirmed), store.build_extraction(confirmed)

    @staticmethod
    def _check_cancelled(cancel_check: CancelCheck) -> None:
        if cancel_check is not None and cancel_check():
            raise ExtractionCancelledError()

    @staticmethod
    def _notify_progress(callback: ProgressCallback, stage: str) -> None:
        if callback is not None:
            callback(stage, None)

    async def _persist_document(
        self,
        command: GuestPayslipExtractionCommand,
        *,
        document_id: UUID | None = None,
    ) -> Document:
        from payroll_copilot.domain.value_objects import PayPeriod
        from payroll_copilot.application.services.employee_document_lifecycle import (
            LIFECYCLE_PROCESSING,
            build_employee_storage_key,
        )

        document_id = document_id or uuid4()
        checksum = hashlib.sha256(command.content).hexdigest()
        org_id = command.organization_id or DEMO_ORGANIZATION_ID
        if command.employee_id is not None:
            storage_key = build_employee_storage_key(
                organization_id=org_id,
                employee_id=command.employee_id,
                document_type=DocumentType.PAYSLIP,
                document_id=document_id,
                filename=command.original_filename or "payslip",
                period_year=command.period_year,
                period_month=command.period_month,
            )
        else:
            storage_key = f"documents/{document_id}/{command.original_filename or 'payslip'}"
        await self._storage.upload(storage_key, command.content, command.mime_type)
        await self._org_bootstrap.ensure_demo_organization(org_id)

        metadata: dict[str, Any] = {
            "document_language": command.language,
            "lifecycle_status": LIFECYCLE_PROCESSING,
            "storage_provider": "s3_compatible",
        }
        if command.metadata_extra:
            metadata.update(command.metadata_extra)
        if command.period_year is not None and command.period_month is not None:
            metadata["selected_period_year"] = command.period_year
            metadata["selected_period_month"] = command.period_month

        period = None
        if command.period_year is not None and command.period_month is not None:
            period = PayPeriod(year=command.period_year, month=command.period_month)

        document = Document(
            id=document_id,
            document_type=DocumentType.PAYSLIP,
            storage_key=storage_key,
            original_filename=command.original_filename or "payslip",
            mime_type=command.mime_type,
            file_size_bytes=len(command.content),
            checksum_sha256=checksum,
            status=DocumentStatus.PROCESSING,
            organization_id=org_id,
            uploaded_by=command.uploaded_by,
            employee_id=command.employee_id,
            period=period,
            metadata=metadata,
            created_at=_utcnow(),
        )
        return await self._documents.save(document)


def _count_usable_fields(fields: list[ExtractedFieldView]) -> int:
    """Count review fields that have a non-empty extracted value."""
    count = 0
    for field in fields:
        if field.status == "MISSING":
            continue
        value = field.value
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        count += 1
    return count


def _fields_from_entries(entries: list[DynamicDocumentEntry]) -> list[ExtractedFieldView]:
    views: list[ExtractedFieldView] = []
    for entry in entries:
        if not is_document_origin_entry(entry):
            continue
        status = "FOUND" if entry.value not in (None, "") else "MISSING"
        views.append(
            ExtractedFieldView(
                key=entry.key,
                value=entry.value,
                confidence=entry.confidence,
                source_text=entry.source_text,
                status=status,
                edited_by_user=False,
                original_value=entry.value,
            )
        )
    return views


def _fields_from_structured(
    structured: dict[str, Any],
) -> tuple[list[ExtractedFieldView], dict[str, float]]:
    """Build field views for pipeline/review via unified Document Model projection."""
    rows = review_rows_from_structured(structured)
    fields = [
        ExtractedFieldView(
            key=str(row["key"]),
            value=row.get("value"),
            confidence=(
                float(row["confidence"])
                if row.get("confidence") is not None
                else None
            ),
            source_text=row.get("source_text"),
            status=str(row.get("status") or "FOUND"),
            edited_by_user=bool(row.get("edited_by_user")),
            original_value=row.get("original_value", row.get("value")),
        )
        for row in rows
        if row.get("key")
    ]
    confidences = {
        str(row["key"]): float(row["confidence"])
        for row in rows
        if row.get("key") and row.get("confidence") is not None
    }
    return fields, confidences
