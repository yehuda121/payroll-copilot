"""Persist user field corrections as a new extraction version."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.exceptions import DocumentNotFoundError
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
)
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.domain.entities import DocumentExtraction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class FieldCorrection:
    key: str
    value: Any
    clear: bool = False


@dataclass(frozen=True, slots=True)
class CorrectExtractionResult:
    extraction_id: UUID
    document_id: UUID
    extraction_version: int
    structured_data: dict[str, Any]
    fields: list[dict[str, Any]]
    language: str = "auto"
    ocr_status: str = "completed"
    parser_status: str = "completed"
    ocr_engine: str | None = None
    parser_model: str | None = None
    warnings: list[str] = field(default_factory=list)


class CorrectGuestExtractionUseCase:
    """Apply user edits without overwriting the original OCR/parser evidence row."""

    def __init__(
        self,
        *,
        document_repository: DocumentRepository,
        extraction_repository: DocumentExtractionRepository,
    ) -> None:
        self._documents = document_repository
        self._extractions = extraction_repository

    async def execute(
        self,
        *,
        document_id: UUID,
        corrections: list[FieldCorrection],
    ) -> CorrectExtractionResult:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)

        previous = await self._extractions.get_latest_for_document(document_id)
        if previous is None:
            raise DocumentNotFoundError(document_id)

        structured = deepcopy(previous.structured_data or {})
        for correction in corrections:
            key = correction.key.strip()
            if not key:
                continue
            if key in {"additional_fields", "parser_notes", "language"}:
                continue

            if key in PAYSLIP_FIELD_KEYS:
                current = structured.get(key) if isinstance(structured.get(key), dict) else {}
                structured[key] = self._apply_edit(current, correction).model_dump(mode="json")
            else:
                additional = structured.setdefault("additional_fields", {})
                if not isinstance(additional, dict):
                    additional = {}
                    structured["additional_fields"] = additional
                current = additional.get(key) if isinstance(additional.get(key), dict) else {}
                additional[key] = self._apply_edit(current, correction).model_dump(mode="json")

        now = _utcnow()
        version = previous.extraction_version + 1
        extraction = DocumentExtraction(
            id=uuid4(),
            document_id=document_id,
            engine=previous.engine,
            raw_text=previous.raw_text,
            structured_data=structured,
            overall_confidence=previous.overall_confidence,
            field_confidences=previous.field_confidences,
            extraction_version=version,
            created_at=now,
            ocr_result=deepcopy(previous.ocr_result or {}),
            parser_model=previous.parser_model,
            language=previous.language,
            ocr_status=previous.ocr_status,
            parser_status=previous.parser_status,
            warnings=list(previous.warnings) + ["User corrected extracted fields."],
            error_message=previous.error_message,
            updated_at=now,
            confirmation_status="review_required",
            confirmed_at=None,
            confirmed_by=None,
        )
        await self._extractions.save(extraction)

        meta = dict(document.metadata or {})
        meta["lifecycle_status"] = "review_required"
        meta["current_extraction_id"] = str(extraction.id)
        meta["current_extraction_version"] = version
        document.metadata = meta
        await self._documents.save(document)

        fields_out: list[dict[str, Any]] = []
        for key in PAYSLIP_FIELD_KEYS:
            payload = structured.get(key)
            if isinstance(payload, dict):
                fields_out.append({"key": key, **payload})
        additional = structured.get("additional_fields") or {}
        if isinstance(additional, dict):
            for key, payload in additional.items():
                if isinstance(payload, dict):
                    fields_out.append({"key": str(key), **payload})

        return CorrectExtractionResult(
            extraction_id=extraction.id,
            document_id=document_id,
            extraction_version=version,
            structured_data=structured,
            fields=fields_out,
            language=previous.language,
            ocr_status=previous.ocr_status,
            parser_status=previous.parser_status,
            ocr_engine=previous.engine,
            parser_model=previous.parser_model,
            warnings=list(dict.fromkeys(list(previous.warnings) + ["User corrected extracted fields."])),
        )

    @staticmethod
    def _apply_edit(current: dict[str, Any], correction: FieldCorrection) -> ExtractedField:
        original_value = current.get("original_value", current.get("value"))
        source_text = current.get("source_text")
        if correction.clear or correction.value is None or correction.value == "":
            return ExtractedField(
                value=None,
                confidence=None,
                source_text=source_text,
                status=FieldExtractionStatus.MISSING,
                edited_by_user=True,
                original_value=original_value,
            )
        return ExtractedField(
            value=correction.value,
            confidence=1.0,
            source_text=source_text,
            status=FieldExtractionStatus.FOUND,
            edited_by_user=True,
            original_value=original_value if original_value is not None else current.get("value"),
        )
