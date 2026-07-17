"""Apply guest field corrections — dynamic entries for landing; DB for legacy."""

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
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    entries_from_payload,
    new_entry,
)
from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
from payroll_copilot.domain.entities import DocumentExtraction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class FieldCorrection:
    key: str
    value: Any
    clear: bool = False


@dataclass(frozen=True, slots=True)
class DynamicEntryPatch:
    """Upsert/delete operations on dynamic document entries."""

    id: str | None = None
    key: str | None = None
    value: Any = None
    delete: bool = False
    add: bool = False


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
    entries: list[dict[str, Any]] = field(default_factory=list)


class CorrectGuestExtractionUseCase:
    """Apply user edits. Guest landing uses ephemeral dynamic entries only."""

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
        corrections: list[FieldCorrection] | None = None,
        entry_patches: list[DynamicEntryPatch] | None = None,
        replace_entries: list[dict[str, Any]] | None = None,
    ) -> CorrectExtractionResult:
        store = get_guest_ephemeral_store()
        ephemeral = store.get(document_id)
        if ephemeral is not None:
            return self._apply_ephemeral(
                ephemeral_document_id=document_id,
                corrections=corrections or [],
                entry_patches=entry_patches or [],
                replace_entries=replace_entries,
            )

        return await self._apply_persisted(
            document_id=document_id,
            corrections=corrections or [],
        )

    def _apply_ephemeral(
        self,
        *,
        ephemeral_document_id: UUID,
        corrections: list[FieldCorrection],
        entry_patches: list[DynamicEntryPatch],
        replace_entries: list[dict[str, Any]] | None,
    ) -> CorrectExtractionResult:
        store = get_guest_ephemeral_store()
        session = store.get(ephemeral_document_id)
        if session is None:
            raise DocumentNotFoundError(ephemeral_document_id)

        # No-op: corrections are optional; return current reviewed document as-is.
        if replace_entries is None and not corrections and not entry_patches:
            entries = entries_from_payload(session.dynamic_entries)
            return self._ephemeral_result(
                ephemeral_document_id=ephemeral_document_id,
                extraction_id=session.extraction_id,
                entries=entries,
                structured_data=session.structured_data or {},
                language=session.language,
                ocr_status=session.ocr_status,
                parser_status=session.parser_status,
                ocr_engine=session.ocr_engine,
                parser_model=session.parser_model,
                warnings=list(session.warnings),
            )

        if replace_entries is not None:
            entries = entries_from_payload(replace_entries)
        else:
            entries = entries_from_payload(session.dynamic_entries)
            entries = self._apply_entry_patches(entries, entry_patches)
            # Legacy key corrections against entry keys
            for correction in corrections:
                key = correction.key.strip()
                if not key:
                    continue
                matched = next((e for e in entries if e.key == key), None)
                if matched is None:
                    if correction.clear:
                        continue
                    entries.append(
                        new_entry(
                            key=key,
                            value=None if correction.clear else correction.value,
                            source="user",
                        )
                    )
                elif correction.clear:
                    matched.value = None
                    matched.source = "user"
                else:
                    matched.value = correction.value
                    matched.source = "user"

        new_extraction_id = uuid4()
        payload = [e.to_dict() for e in entries]
        updated = store.update_dynamic_entries(
            ephemeral_document_id,
            dynamic_entries=payload,
            warnings=["User corrected extracted fields."],
            extraction_id=new_extraction_id,
        )
        assert updated is not None

        return self._ephemeral_result(
            ephemeral_document_id=ephemeral_document_id,
            extraction_id=updated.extraction_id,
            entries=entries,
            structured_data=updated.structured_data or {},
            language=updated.language,
            ocr_status=updated.ocr_status,
            parser_status=updated.parser_status,
            ocr_engine=updated.ocr_engine,
            parser_model=updated.parser_model,
            warnings=list(updated.warnings),
        )

    @staticmethod
    def _ephemeral_result(
        *,
        ephemeral_document_id: UUID,
        extraction_id: UUID,
        entries: list[DynamicDocumentEntry],
        structured_data: dict[str, Any],
        language: str,
        ocr_status: str,
        parser_status: str,
        ocr_engine: str | None,
        parser_model: str | None,
        warnings: list[str],
    ) -> CorrectExtractionResult:
        payload = [e.to_dict() for e in entries]
        fields_out = [
            {
                "key": e.key,
                "value": e.value,
                "confidence": e.confidence,
                "source_text": e.source_text,
                "status": "FOUND" if e.value not in (None, "") else "MISSING",
                "edited_by_user": e.source == "user",
            }
            for e in entries
        ]
        return CorrectExtractionResult(
            extraction_id=extraction_id,
            document_id=ephemeral_document_id,
            extraction_version=1,
            structured_data=structured_data,
            fields=fields_out,
            language=language,
            ocr_status=ocr_status,
            parser_status=parser_status,
            ocr_engine=ocr_engine,
            parser_model=parser_model,
            warnings=warnings,
            entries=payload,
        )

    @staticmethod
    def _apply_entry_patches(
        entries: list[DynamicDocumentEntry],
        patches: list[DynamicEntryPatch],
    ) -> list[DynamicDocumentEntry]:
        by_id = {e.id: e for e in entries}
        for patch in patches:
            if patch.add:
                entries.append(
                    new_entry(
                        key=patch.key or "",
                        value=patch.value,
                        source="user",
                        kind="field",
                    )
                )
                continue
            if not patch.id or patch.id not in by_id:
                continue
            target = by_id[patch.id]
            if patch.delete:
                entries = [e for e in entries if e.id != patch.id]
                by_id.pop(patch.id, None)
                continue
            if patch.key is not None:
                target.key = patch.key.strip() or target.key
            if patch.value is not None or patch.key is not None:
                # Allow explicit null clear via value=None when provided in patch
                target.value = patch.value
                target.source = "user"
        return entries

    async def _apply_persisted(
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
        structured = self._apply_corrections(structured, corrections)

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

        return CorrectExtractionResult(
            extraction_id=extraction.id,
            document_id=document_id,
            extraction_version=version,
            structured_data=structured,
            fields=self._fields_out(structured),
            language=previous.language,
            ocr_status=previous.ocr_status,
            parser_status=previous.parser_status,
            ocr_engine=previous.engine,
            parser_model=previous.parser_model,
            warnings=list(dict.fromkeys(list(previous.warnings) + ["User corrected extracted fields."])),
            entries=[],
        )

    def _apply_corrections(
        self,
        structured: dict[str, Any],
        corrections: list[FieldCorrection],
    ) -> dict[str, Any]:
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
        return structured

    @staticmethod
    def _fields_out(structured: dict[str, Any]) -> list[dict[str, Any]]:
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
        return fields_out

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
