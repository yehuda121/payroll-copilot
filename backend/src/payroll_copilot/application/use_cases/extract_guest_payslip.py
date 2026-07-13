"""Guest payslip extraction orchestration (OCR → AI Parser → persist).

Does not run Rule Engine / deterministic validation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.exceptions import (
    OcrError,
    PayslipParserError,
)
from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
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
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


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


@dataclass(frozen=True, slots=True)
class GuestPayslipExtractionCommand:
    content: bytes
    original_filename: str
    mime_type: str
    language: str = "auto"


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
        document = await self._persist_document(command)
        warnings: list[str] = []
        ocr_status = "pending"
        parser_status = "pending"
        ocr_engine: str | None = None
        parser_model: str | None = None
        raw_text = ""
        ocr_payload: dict[str, Any] = {}
        structured: dict[str, Any] = {}
        field_confidences: dict[str, float] = {}
        fields: list[ExtractedFieldView] = []
        error_message: str | None = None
        language = command.language

        try:
            ocr_result = await self._ocr.execute(
                ExtractDocumentTextCommand(
                    content=command.content,
                    filename=command.original_filename,
                    content_type=command.mime_type,
                    language=command.language,
                )
            )
            ocr_status = "completed"
            ocr_engine = ocr_result.engine
            language = ocr_result.language_effective or ocr_result.language_requested or command.language
            raw_text = ocr_result.raw_text
            warnings.extend(list(ocr_result.warnings))
            ocr_payload = {
                "engine": ocr_result.engine,
                "language_requested": ocr_result.language_requested,
                "language_effective": ocr_result.language_effective,
                "overall_confidence": ocr_result.overall_confidence,
                "raw_text": ocr_result.raw_text,
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

            try:
                parse_result = await self._parse.execute(command_from_ocr_result(ocr_result))
                parser_status = "completed"
                parser_model = parse_result.model
                warnings.extend(list(parse_result.warnings))
                if parse_result.retry_used:
                    warnings.append("Parser retried once after an invalid response.")
                structured = parse_result.fields.model_dump(mode="json")
                fields, field_confidences = _fields_from_structured(structured)
            except PayslipParserError as exc:
                parser_status = "failed"
                error_message = exc.message
                warnings.append(exc.message)
        except OcrError as exc:
            ocr_status = "failed"
            parser_status = "skipped"
            error_message = exc.message
            warnings.append(exc.message)

        document.status = (
            DocumentStatus.PROCESSED
            if ocr_status == "completed" and parser_status == "completed"
            else DocumentStatus.FAILED
            if ocr_status == "failed" or parser_status == "failed"
            else DocumentStatus.PROCESSING
        )
        document.metadata = {
            **document.metadata,
            "document_language": language,
            "ocr_status": ocr_status,
            "parser_status": parser_status,
            "extraction_connected": parser_status == "completed",
        }
        await self._documents.save(document)

        previous = await self._extractions.get_latest_for_document(document.id)
        version = (previous.extraction_version + 1) if previous else 1
        now = _utcnow()
        extraction = DocumentExtraction(
            id=uuid4(),
            document_id=document.id,
            engine=ocr_engine or "unknown",
            raw_text=raw_text,
            structured_data=structured,
            overall_confidence=None,
            field_confidences=field_confidences,
            extraction_version=version,
            created_at=now,
            ocr_result=ocr_payload,
            parser_model=parser_model,
            language=language,
            ocr_status=ocr_status,
            parser_status=parser_status,
            warnings=list(dict.fromkeys(warnings)),
            error_message=error_message,
            updated_at=now,
        )
        await self._extractions.save(extraction)

        if not fields and structured:
            fields, _ = _fields_from_structured(structured)

        return GuestPayslipExtractionResult(
            document_id=document.id,
            extraction_id=extraction.id,
            ocr_status=ocr_status,
            parser_status=parser_status,
            language=language,
            ocr_engine=ocr_engine,
            parser_model=parser_model,
            warnings=list(dict.fromkeys(warnings)),
            fields=fields,
            raw_text=raw_text,
            error_message=error_message,
        )

    async def _persist_document(self, command: GuestPayslipExtractionCommand) -> Document:
        document_id = uuid4()
        checksum = hashlib.sha256(command.content).hexdigest()
        storage_key = f"documents/{document_id}/{command.original_filename or 'payslip'}"
        await self._storage.upload(storage_key, command.content, command.mime_type)
        await self._org_bootstrap.ensure_demo_organization(DEMO_ORGANIZATION_ID)

        document = Document(
            id=document_id,
            document_type=DocumentType.PAYSLIP,
            storage_key=storage_key,
            original_filename=command.original_filename or "payslip",
            mime_type=command.mime_type,
            file_size_bytes=len(command.content),
            checksum_sha256=checksum,
            status=DocumentStatus.PROCESSING,
            organization_id=DEMO_ORGANIZATION_ID,
            metadata={"document_language": command.language},
            created_at=_utcnow(),
        )
        return await self._documents.save(document)


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
