"""Guest payslip extraction orchestration (OCR → AI Parser → persist).

Does not run Rule Engine / deterministic validation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.exceptions import (
    ExtractionCancelledError,
    OcrError,
    PayslipParserError,
)
from payroll_copilot.application.ports.layout import LayoutBuildRequest, LayoutSnapshotConfig
from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_have_usable_values,
    map_dynamic_entries_to_structured,
)
from payroll_copilot.application.services.guest_dynamic_extractor import GuestDynamicDocumentExtractor
from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    get_guest_ephemeral_store,
)
from payroll_copilot.application.services.layout_analysis_pipeline import (
    build_layout_analysis,
    create_layout_structure_config,
)
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
    ExtractDocumentTextUseCase,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
    command_from_ocr_result,
)
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType
from payroll_copilot.application.services.text_normalize import normalize_extracted_text
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.layout.hybrid_layout_provider import (
    HybridLayoutProvider,
    create_layout_provider,
)
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
    # Optional employee binding — used by employee extract path; guest leaves unset.
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


class ExtractGuestPayslipUseCase:
    """Upload payslip bytes, run OCR + parser, persist extraction, return fields."""

    def __init__(
        self,
        *,
        document_repository: DocumentRepository,
        extraction_repository: DocumentExtractionRepository,
        object_storage: ObjectStoragePort,
        organization_bootstrap: OrganizationBootstrapPort,
        ocr_use_case: ExtractDocumentTextUseCase,
        parse_use_case: ParsePayslipFromOcrUseCase,
    ) -> None:
        self._documents = document_repository
        self._extractions = extraction_repository
        self._storage = object_storage
        self._org_bootstrap = organization_bootstrap
        self._ocr = ocr_use_case
        self._parse = parse_use_case

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
                # Keep existing storage object; content is used only for OCR/parser.
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
            self._notify_progress(command.progress_callback, "ocr")
            ocr_result = await self._ocr.execute(
                ExtractDocumentTextCommand(
                    content=command.content,
                    filename=command.original_filename,
                    content_type=command.mime_type,
                    language=command.language,
                )
            )
            timer.log_stage(
                "ocr_completed" if "tesseract" in (ocr_result.engine or "") and "pdf_text" not in (ocr_result.engine or "") else "embedded_pdf_text",
                page_count=len(ocr_result.pages),
                extracted_text_length=len(ocr_result.raw_text or ""),
            )
            ocr_status = "completed"
            ocr_engine = ocr_result.engine
            language = ocr_result.language_effective or ocr_result.language_requested or command.language
            raw_text = normalize_extracted_text(ocr_result.raw_text)
            warnings.extend(list(ocr_result.warnings))
            ocr_payload = _ocr_payload_from_result(ocr_result, raw_text=raw_text)
            layout_snapshot = _build_layout_snapshot(
                content=command.content,
                mime_type=command.mime_type,
                filename=command.original_filename,
                ocr_result=ocr_result,
            )
            layout_analysis = _build_layout_analysis(
                layout_snapshot=layout_snapshot,
                content=command.content,
                mime_type=command.mime_type,
                filename=command.original_filename,
                ocr_result=ocr_result,
            )
            timer.log_stage("text_normalization", extracted_text_length=len(raw_text))

            self._check_cancelled(command.cancel_check)
            try:
                self._notify_progress(command.progress_callback, "extracting")
                if use_ephemeral:
                    # Landing page: document-first dynamic key/value extraction.
                    extractor = GuestDynamicDocumentExtractor()
                    pages_text = [page.text for page in ocr_result.pages] if ocr_result.pages else None
                    dynamic_entries, model_name, dyn_warnings = await extractor.extract(
                        ocr_text=raw_text,
                        language=language,
                        pages_text=pages_text,
                    )
                    parser_model = model_name
                    warnings.extend(dyn_warnings)
                    if not entries_have_usable_values(dynamic_entries):
                        parser_status = "failed"
                        error_message = "We could not extract usable information from this document."
                        warnings.append("dynamic_extractor_no_usable_entries")
                        fields = []
                        field_confidences = {}
                        structured = {}
                    else:
                        parser_status = "completed"
                        fields = [
                            ExtractedFieldView(
                                key=entry.key,
                                value=entry.value,
                                confidence=entry.confidence,
                                source_text=entry.source_text,
                                status="FOUND"
                                if entry.value not in (None, "")
                                else "MISSING",
                            )
                            for entry in dynamic_entries
                        ]
                        field_confidences = {
                            entry.key: entry.confidence
                            for entry in dynamic_entries
                            if entry.confidence is not None
                        }
                        # Canonical structured_data is filled only after confirm.
                        structured = {"dynamic_entries": [e.to_dict() for e in dynamic_entries]}
                    timer.log_stage(
                        "dynamic_extraction",
                        page_count=len(ocr_result.pages),
                        extracted_text_length=len(raw_text),
                        extracted_field_count=len(fields),
                    )
                else:
                    parse_result = await self._parse.execute(
                        command_from_ocr_result(
                            ocr_result,
                            cancel_check=command.cancel_check,
                            simple_guest_fields=False,
                            layout_analysis=layout_analysis,
                        )
                    )
                    parser_status = "completed"
                    parser_model = parse_result.model
                    warnings.extend(list(parse_result.warnings))
                    if parse_result.retry_used:
                        warnings.append("Parser retried once after an invalid response.")
                    structured = parse_result.fields.model_dump(mode="json")
                    fields, field_confidences = _fields_from_structured(structured)
                    usable_count = _count_usable_fields(fields)
                    timer.log_stage(
                        "semantic_mapping",
                        page_count=len(ocr_result.pages),
                        extracted_text_length=len(raw_text),
                        extracted_field_count=usable_count,
                    )
                    if usable_count == 0:
                        parser_status = "failed"
                        error_message = "We could not extract usable information from this document."
                        warnings.append("parser_no_usable_fields")
                        timer.log_stage(
                            "parser_empty_fields",
                            page_count=len(ocr_result.pages),
                            extracted_text_length=len(raw_text),
                            extracted_field_count=0,
                            error_code="parser_no_usable_fields",
                        )
                    dynamic_entries = []
            except PayslipParserError as exc:
                parser_status = "failed"
                error_message = exc.message
                warnings.append(exc.message)
                dynamic_entries = []
                timer.log_stage(
                    "parser_failed",
                    page_count=len(ocr_result.pages),
                    extracted_text_length=len(raw_text),
                    extracted_field_count=0,
                    error_code="parser_error",
                )
        except ExtractionCancelledError:
            timer.log_stage("extraction_cancelled", error_code="extraction_cancelled")
            raise
        except OcrError as exc:
            ocr_status = "failed"
            parser_status = "skipped"
            error_message = exc.message
            warnings.append(exc.message)
            timer.log_stage("ocr_failed", error_code=exc.code)

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
                dynamic_entries=[entry.to_dict() for entry in dynamic_entries],
                ocr_result=ocr_payload,
                warnings=list(dict.fromkeys(warnings)),
                error_message=error_message,
                field_confidences=field_confidences,
            )
            get_guest_ephemeral_store(ttl_hours=get_settings().guest_ephemeral_ttl_hours).save(session)
            timer.log_stage("persistence_ephemeral")
        else:
            assert document is not None
            from payroll_copilot.application.services.employee_document_lifecycle import (
                LIFECYCLE_EXTRACTION_COMPLETED,
                LIFECYCLE_EXTRACTION_FAILED,
                LIFECYCLE_REVIEW_REQUIRED,
            )

            document.status = (
                DocumentStatus.PROCESSED
                if ocr_status == "completed" and parser_status == "completed"
                else DocumentStatus.FAILED
                if ocr_status == "failed" or parser_status == "failed"
                else DocumentStatus.PROCESSING
            )
            lifecycle = (
                LIFECYCLE_REVIEW_REQUIRED
                if parser_status == "completed"
                else LIFECYCLE_EXTRACTION_FAILED
                if parser_status == "failed" or ocr_status == "failed"
                else LIFECYCLE_EXTRACTION_COMPLETED
            )
            document.metadata = {
                **document.metadata,
                "document_language": language,
                "ocr_status": ocr_status,
                "parser_status": parser_status,
                "extraction_connected": parser_status == "completed",
                "lifecycle_status": lifecycle,
            }
            await self._documents.save(document)

            previous = await self._extractions.get_latest_for_document(document.id)
            version = (previous.extraction_version + 1) if previous else 1
            now = _utcnow()
            extraction = DocumentExtraction(
                id=extraction_id,
                document_id=document.id,
                engine=ocr_engine or "unknown",
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
                **document.metadata,
                "current_extraction_id": str(extraction.id),
                "current_extraction_version": version,
            }
            await self._documents.save(document)
            timer.log_stage("persistence")

        timer.log_summary()

        if not fields and structured:
            fields, _ = _fields_from_structured(structured)

        return GuestPayslipExtractionResult(
            document_id=document.id if document is not None else document_id,
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
            entries=dynamic_entries if use_ephemeral else None,
        )

    def confirm_ephemeral_session(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any] | None = None,
        dynamic_entries: list[dict[str, Any]] | None = None,
    ) -> tuple[Document, DocumentExtraction]:
        """Map confirmed dynamic entries → canonical structured_data, then freeze.

        Never writes permanent S3/DB. Validation reads the mapped structured_data.
        """
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
        mapped, map_warnings = map_dynamic_entries_to_structured(entries)
        if structured_data is not None:
            mapped = structured_data
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

        document_id = document_id or uuid4()
        checksum = hashlib.sha256(command.content).hexdigest()
        from payroll_copilot.application.services.employee_document_lifecycle import (
            LIFECYCLE_PROCESSING,
            build_employee_storage_key,
        )

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


def _ocr_payload_from_result(ocr_result, *, raw_text: str) -> dict[str, Any]:
    return {
        "engine": ocr_result.engine,
        "language_requested": ocr_result.language_requested,
        "language_effective": ocr_result.language_effective,
        "overall_confidence": ocr_result.overall_confidence,
        "raw_text": raw_text,
        "warnings": list(ocr_result.warnings),
        "pages": [
            {
                "page": page.page,
                "language": page.language,
                "text": page.text,
                "confidence": page.confidence,
                "lines": [
                    {
                        "text": line.text,
                        "confidence": line.confidence,
                        "bbox": list(line.bbox) if line.bbox else None,
                        "words": [
                            {
                                "text": word.text,
                                "confidence": word.confidence,
                                "bbox": list(word.bbox),
                                "block_number": word.block_number,
                                "paragraph_number": word.paragraph_number,
                                "line_number": word.line_number,
                                "word_number": word.word_number,
                            }
                            for word in line.words
                        ],
                    }
                    for line in page.lines
                ],
                "words": [
                    {
                        "text": word.text,
                        "confidence": word.confidence,
                        "bbox": list(word.bbox),
                        "block_number": word.block_number,
                        "paragraph_number": word.paragraph_number,
                        "line_number": word.line_number,
                        "word_number": word.word_number,
                    }
                    for word in page.words
                ],
            }
            for page in ocr_result.pages
        ],
    }


def _build_layout_snapshot(
    *,
    content: bytes,
    mime_type: str,
    filename: str | None,
    ocr_result,
) -> dict[str, Any]:
    """Phase 1 additive layout metadata. Never affects parser inputs or structured_data."""
    settings = get_settings()
    if not getattr(settings, "layout_snapshot_enabled", False):
        return {}
    try:
        provider = create_layout_provider(settings)
        return provider.build(
            LayoutBuildRequest(
                content=content,
                media_type=mime_type,
                ocr_result=ocr_result,
                filename=filename,
            )
        )
    except Exception:  # noqa: BLE001
        # Layout must never fail extraction. Empty snapshot keeps consumers stable.
        return {
            "schema_version": 1,
            "provider": "hybrid_layout_v1",
            "source": "unavailable",
            "coordinate_format": "xywh",
            "coordinate_space": "unknown",
            "engine": getattr(ocr_result, "engine", None),
            "page_count": 0,
            "truncated": False,
            "pages": [],
            "warnings": ["layout_snapshot_build_failed"],
        }


def _build_layout_analysis(
    *,
    layout_snapshot: dict[str, Any],
    content: bytes,
    mime_type: str,
    filename: str | None,
    ocr_result,
) -> dict[str, Any]:
    """Phase 2 additive structure + associations. Also runs when Phase 3 needs candidates."""
    settings = get_settings()
    structure_config = create_layout_structure_config(settings)
    evidence_bound = bool(getattr(settings, "payslip_parser_evidence_bound_enabled", False))
    if not structure_config.enabled and not evidence_bound:
        return {}

    # Phase 3 may enable analysis without persisting Phase 2 flag permanently.
    if evidence_bound and not structure_config.enabled:
        from payroll_copilot.application.ports.structure_association import LayoutStructureConfig

        structure_config = LayoutStructureConfig(enabled=True)

    snapshot = layout_snapshot
    # Build an in-memory layout when Phase 1 persist flag is off.
    if not snapshot or not (snapshot.get("pages") or []):
        try:
            provider = HybridLayoutProvider(
                LayoutSnapshotConfig(
                    enabled=True,
                    include_words=bool(getattr(settings, "layout_snapshot_include_words", True)),
                    max_pages=int(getattr(settings, "layout_snapshot_max_pages", 20)),
                    max_words=int(getattr(settings, "layout_snapshot_max_words", 8_000)),
                    max_lines=int(getattr(settings, "layout_snapshot_max_lines", 2_000)),
                )
            )
            snapshot = provider.build(
                LayoutBuildRequest(
                    content=content,
                    media_type=mime_type,
                    ocr_result=ocr_result,
                    filename=filename,
                )
            )
        except Exception:  # noqa: BLE001
            snapshot = {}

    return build_layout_analysis(snapshot, config=structure_config)


def _fields_from_structured(structured: dict[str, Any]) -> tuple[list[ExtractedFieldView], dict[str, float]]:
    fields: list[ExtractedFieldView] = []
    confidences: dict[str, float] = {}

    additional = structured.get("additional_fields") or {}
    keys = [k for k in structured.keys() if k not in {"additional_fields", "parser_notes", "language"}]
    for key in keys:
        payload = structured.get(key)
        view = _field_view(key, payload)
        fields.append(view)
        if view.confidence is not None and view.status in {"FOUND", "UNCERTAIN"}:
            confidences[key] = view.confidence

    if isinstance(additional, dict):
        for key, payload in additional.items():
            view = _field_view(str(key), payload)
            fields.append(view)
            if view.confidence is not None and view.status in {"FOUND", "UNCERTAIN"}:
                confidences[str(key)] = view.confidence

    return fields, confidences


def _count_usable_fields(fields: list[ExtractedFieldView]) -> int:
    """Count fields with a non-empty value (FOUND or UNCERTAIN)."""
    usable = 0
    for field in fields:
        if field.status not in {"FOUND", "UNCERTAIN"}:
            continue
        if field.value is None or field.value == "":
            continue
        usable += 1
    return usable


def _field_view(key: str, payload: Any) -> ExtractedFieldView:
    if not isinstance(payload, dict):
        return ExtractedFieldView(
            key=key,
            value=payload,
            confidence=None,
            source_text=None,
            status="MISSING",
        )
    status = str(payload.get("status") or "MISSING").upper()
    conf = payload.get("confidence")
    confidence: float | None
    try:
        confidence = float(conf) if conf is not None and conf != "" else None
        if confidence is not None and (confidence < 0 or confidence > 1):
            confidence = None
    except (TypeError, ValueError):
        confidence = None
    if status == "MISSING":
        confidence = None
    return ExtractedFieldView(
        key=key,
        value=payload.get("value"),
        confidence=confidence,
        source_text=payload.get("source_text"),
        status=status,
        edited_by_user=bool(payload.get("edited_by_user", False)),
        original_value=payload.get("original_value"),
    )
