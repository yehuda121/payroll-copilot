"""Employee document storage key helpers and field effective-value mapping."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from payroll_copilot.domain.enums import DocumentType

LIFECYCLE_UPLOADED = "uploaded"
LIFECYCLE_PROCESSING = "processing"
LIFECYCLE_EXTRACTION_COMPLETED = "extraction_completed"
LIFECYCLE_EXTRACTION_FAILED = "extraction_failed"
LIFECYCLE_REVIEW_REQUIRED = "review_required"
LIFECYCLE_ACCOUNTANT_REVIEW = "accountant_review"
LIFECYCLE_CONFIRMED = "confirmed"
LIFECYCLE_PUBLISHED = "published"
LIFECYCLE_SUPERSEDED = "superseded"

CONFIRMATION_REVIEW_REQUIRED = "review_required"
CONFIRMATION_CONFIRMED = "confirmed"

PUBLICATION_DRAFT = "draft"
PUBLICATION_PUBLISHED = "published"

MONTHLY_TYPES = {DocumentType.PAYSLIP, DocumentType.ATTENDANCE}
PERSISTENT_TYPES = {
    DocumentType.NATIONAL_ID,
    DocumentType.ID_APPENDIX,
    DocumentType.CONTRACT,
}


def is_employee_visible_document(document: Any) -> bool:
    """Return false for accountant batch drafts, including provisionally matched ones."""
    metadata = dict(getattr(document, "metadata", None) or {})
    publication = metadata.get("publication_status")
    if metadata.get("source") == "accountant_bulk_upload":
        return publication == PUBLICATION_PUBLISHED
    return publication != PUBLICATION_DRAFT


def build_employee_storage_key(
    *,
    organization_id: UUID,
    employee_id: UUID,
    document_type: DocumentType | str,
    document_id: UUID,
    filename: str,
    period_year: int | None = None,
    period_month: int | None = None,
) -> str:
    """Stable logical object key for employee-owned documents (S3/MinIO compatible)."""
    safe_name = (filename or "upload").replace("\\", "/").split("/")[-1] or "upload"
    dtype = document_type.value if hasattr(document_type, "value") else str(document_type)
    org = str(organization_id)
    emp = str(employee_id)
    doc = str(document_id)
    if period_year and period_month and dtype in {t.value for t in MONTHLY_TYPES} | {
        DocumentType.PAYSLIP.value,
        DocumentType.ATTENDANCE.value,
    }:
        return (
            f"organizations/{org}/employees/{emp}/payroll/"
            f"{period_year}/{period_month:02d}/{dtype}/{doc}/{safe_name}"
        )
    return f"organizations/{org}/employees/{emp}/documents/{dtype}/{doc}/{safe_name}"


def field_view_from_payload(key: str, payload: Any) -> dict[str, Any]:
    """Map structured extraction field into extracted/corrected/effective presentation."""
    if not isinstance(payload, dict):
        return {
            "key": key,
            "extracted_value": payload,
            "corrected_value": None,
            "effective_value": payload,
            "confidence": None,
            "extraction_status": "MISSING" if payload in (None, "") else "FOUND",
            "source_text": None,
            "edited_by_employee": False,
            "confirmed": False,
        }
    edited = bool(payload.get("edited_by_user"))
    current = payload.get("value")
    original = payload.get("original_value")
    if edited:
        extracted_value = original if original is not None else None
        corrected_value = current
    else:
        extracted_value = current
        corrected_value = None
    effective = corrected_value if edited else extracted_value
    return {
        "key": key,
        "extracted_value": extracted_value,
        "corrected_value": corrected_value,
        "effective_value": effective,
        "confidence": payload.get("confidence"),
        "extraction_status": str(payload.get("status") or "MISSING").upper(),
        "source_text": payload.get("source_text"),
        "evidence_ids": payload.get("evidence_ids") or [],
        "edited_by_employee": edited,
        "confirmed": bool(payload.get("confirmed")),
    }


def fields_from_structured(structured: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Canonical (+ additional) field views for identity/validation chrome.

    Skips Document Model payload (``dynamic_entries``) so it is never treated
    as a payroll field key.
    """
    structured = structured or {}
    fields: list[dict[str, Any]] = []
    for key, payload in structured.items():
        if key in {"additional_fields", "parser_notes", "language", "dynamic_entries"}:
            continue
        fields.append(field_view_from_payload(str(key), payload))
    additional = structured.get("additional_fields")
    if isinstance(additional, dict):
        for key, payload in additional.items():
            fields.append(field_view_from_payload(str(key), payload))
    return fields


def review_fields_from_structured(structured: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Review SoT: Document Model entries when present, else non-empty canonical fields."""
    from payroll_copilot.application.services.dynamic_document import (
        entries_from_structured,
        is_document_origin_entry,
    )

    entries = entries_from_structured(structured)
    if entries:
        out: list[dict[str, Any]] = []
        for entry in entries:
            if not is_document_origin_entry(entry):
                continue
            out.append(
                {
                    "key": entry.key,
                    "extracted_value": entry.value,
                    "corrected_value": None,
                    "effective_value": entry.value,
                    "confidence": entry.confidence,
                    "extraction_status": (
                        "FOUND" if entry.value not in (None, "") else "MISSING"
                    ),
                    "source_text": entry.source_text,
                    "edited_by_employee": entry.source == "user",
                    "confirmed": False,
                    "section": entry.section,
                    "kind": entry.kind,
                    "table_id": entry.table_id,
                    "row_index": entry.row_index,
                    "column": entry.column,
                    "entry_id": entry.id,
                    "page": entry.page,
                }
            )
        return out

    # Legacy extractions without Document Model: omit empty MISSING placeholders.
    return [
        row
        for row in fields_from_structured(structured)
        if str(row.get("extraction_status") or "").upper() in {"FOUND", "UNCERTAIN"}
        or row.get("effective_value") not in (None, "")
    ]
