"""Dynamic document entries for guest landing extraction (document-first).

Extraction produces a complete Document Model (label/value pairs plus optional
section/table metadata as found on the document).

Canonical payroll fields are produced only after user confirmation via mapping.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
)


@dataclass
class DynamicDocumentEntry:
    """One editable key/value pair extracted from a document.

    Optional section/table metadata preserves document structure for review and
    future UI. Mapping/validation ignore these fields and use key/value only.
    """

    id: str
    key: str
    value: Any
    confidence: float | None = None
    page: int | None = None
    source: str = "ocr"
    source_text: str | None = None
    section: str | None = None
    kind: str | None = None
    table_id: str | None = None
    row_index: int | None = None
    column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DynamicDocumentEntry:
        conf = raw.get("confidence")
        confidence: float | None
        try:
            confidence = float(conf) if conf is not None and conf != "" else None
            if confidence is not None and (confidence < 0 or confidence > 1):
                confidence = None
        except (TypeError, ValueError):
            confidence = None
        page_raw = raw.get("page")
        page: int | None
        try:
            page = int(page_raw) if page_raw is not None and page_raw != "" else None
        except (TypeError, ValueError):
            page = None
        row_raw = raw.get("row_index")
        row_index: int | None
        try:
            row_index = int(row_raw) if row_raw is not None and row_raw != "" else None
        except (TypeError, ValueError):
            row_index = None

        section = raw.get("section")
        kind = raw.get("kind")
        table_id = raw.get("table_id")
        column = raw.get("column")
        return cls(
            id=str(raw.get("id") or uuid4()),
            key=str(raw.get("key") or "").strip(),
            value=raw.get("value"),
            confidence=confidence,
            page=page,
            source=str(raw.get("source") or "ocr"),
            source_text=raw.get("source_text") if isinstance(raw.get("source_text"), str) else None,
            section=str(section).strip() if isinstance(section, str) and section.strip() else None,
            kind=str(kind).strip() if isinstance(kind, str) and kind.strip() else None,
            table_id=str(table_id).strip() if isinstance(table_id, str) and table_id.strip() else None,
            row_index=row_index,
            column=str(column).strip() if isinstance(column, str) and column.strip() else None,
        )


def new_entry(
    *,
    key: str,
    value: Any = None,
    confidence: float | None = None,
    page: int | None = None,
    source: str = "ocr",
    source_text: str | None = None,
    section: str | None = None,
    kind: str | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
    column: str | None = None,
) -> DynamicDocumentEntry:
    return DynamicDocumentEntry(
        id=str(uuid4()),
        key=key.strip(),
        value=value,
        confidence=confidence,
        page=page,
        source=source,
        source_text=source_text,
        section=section.strip() if isinstance(section, str) and section.strip() else None,
        kind=kind.strip() if isinstance(kind, str) and kind.strip() else None,
        table_id=table_id.strip() if isinstance(table_id, str) and table_id.strip() else None,
        row_index=row_index,
        column=column.strip() if isinstance(column, str) and column.strip() else None,
    )


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def is_document_origin_entry(entry: DynamicDocumentEntry) -> bool:
    """Keep rows that came from the document (label and/or value). Drop blanks."""
    if not (bool(entry.key.strip()) or _has_value(entry.value)):
        return False
    # Drop empty snake_case schema placeholders the model may invent.
    if not _has_value(entry.value):
        key = entry.key.strip()
        if key in PAYSLIP_FIELD_KEYS or key in {"national_id", "total_deductions"}:
            return False
    return True


def entries_from_payload(raw: Any) -> list[DynamicDocumentEntry]:
    if not isinstance(raw, list):
        return []
    out: list[DynamicDocumentEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = DynamicDocumentEntry.from_dict(item)
        if not is_document_origin_entry(entry):
            continue
        out.append(entry)
    return out


def entries_have_usable_values(entries: list[DynamicDocumentEntry]) -> bool:
    return any(_has_value(entry.value) for entry in entries)


# ---------------------------------------------------------------------------
# Canonical mapping (post-confirm only)
# ---------------------------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[^a-z0-9\u0590-\u05ff\u0600-\u06ff]+", re.UNICODE)


def _normalize_label(label: str) -> str:
    text = label.strip().casefold()
    text = text.replace("ת.ז", "תז").replace("ת״ז", "תז").replace("ת'ז", "תז")
    text = _NORMALIZE_RE.sub(" ", text)
    return " ".join(text.split())


# Synonyms → canonical PAYSLIP_FIELD_KEYS (or well-known extras kept in additional_fields).
_LABEL_TO_CANONICAL: dict[str, str] = {
    # employee name
    "employee name": "employee_name",
    "full name": "employee_name",
    "worker name": "employee_name",
    "name": "employee_name",
    "שם עובד": "employee_name",
    "שם העובד": "employee_name",
    "שם": "employee_name",
    # employee id / number
    "employee id": "employee_id",
    "employee number": "employee_number",
    "employee no": "employee_number",
    "personnel number": "employee_number",
    "personnel no": "employee_number",
    "file number": "employee_number",
    "worker code": "employee_number",
    "worker number": "employee_number",
    "worker id": "employee_id",
    "מספר עובד": "employee_number",
    "מס עובד": "employee_number",
    "מספר אישי": "employee_number",
    "מספר תיק": "employee_number",
    # national id
    "national id": "national_id",
    "id number": "national_id",
    "identity number": "national_id",
    "teudat zehut": "national_id",
    "תז": "national_id",
    "תעודת זהות": "national_id",
    "מספר זהות": "national_id",
    # period
    "pay period": "pay_period",
    "payroll month": "pay_period",
    "payroll period": "pay_period",
    "salary month": "pay_period",
    "period": "pay_period",
    "month": "pay_period",
    "תקופת שכר": "pay_period",
    "חודש שכר": "pay_period",
    "חודש": "pay_period",
    "לתקופה": "pay_period",
    # money
    "gross salary": "gross_salary",
    "gross pay": "gross_salary",
    "gross": "gross_salary",
    "total payments": "gross_salary",
    "שכר ברוטו": "gross_salary",
    "ברוטו": "gross_salary",
    "סהכ תשלומים": "gross_salary",
    "סך תשלומים": "gross_salary",
    "net salary": "net_salary",
    "net pay": "net_salary",
    "net": "net_salary",
    "שכר נטו": "net_salary",
    "נטו": "net_salary",
    "base salary": "base_salary",
    "basic salary": "base_salary",
    "שכר יסוד": "base_salary",
    "שכר בסיס": "base_salary",
    # deductions / taxes
    "income tax": "income_tax",
    "tax": "income_tax",
    "מס הכנסה": "income_tax",
    "national insurance": "national_insurance",
    "ביטוח לאומי": "national_insurance",
    "health tax": "health_tax",
    "מס בריאות": "health_tax",
    "pension": "pension_employee",
    "pension employee": "pension_employee",
    "פנסיה": "pension_employee",
    "total deductions": "total_deductions",
    "סך ניכויים": "total_deductions",
    "סהכ ניכויים": "total_deductions",
    # hours / rates
    "regular hours": "regular_hours",
    "hours": "regular_hours",
    "שעות רגילות": "regular_hours",
    "overtime hours": "overtime_hours",
    "שעות נוספות": "overtime_hours",
    "hourly rate": "hourly_rate",
    "תעריף לשעה": "hourly_rate",
    # other
    "department": "department",
    "מחלקה": "department",
    "payment method": "payment_method",
    "bank transfer": "payment_method",
    "אמצעי תשלום": "payment_method",
    "העברה בנקאית": "payment_method",
    "travel": "travel_expenses",
    "travel expenses": "travel_expenses",
    "נסיעות": "travel_expenses",
    "vacation balance": "vacation_balance",
    "יתרת חופשה": "vacation_balance",
    "sick leave": "sick_leave_balance",
    "יתרת מחלה": "sick_leave_balance",
    "employment type": "employment_type",
    "סוג העסקה": "employment_type",
}


def resolve_canonical_key(label: str) -> str | None:
    """Map a document label to a canonical key, or None if unknown."""
    normalized = _normalize_label(label)
    if not normalized:
        return None
    if normalized in _LABEL_TO_CANONICAL:
        return _LABEL_TO_CANONICAL[normalized]
    # Compact form without spaces
    compact = normalized.replace(" ", "")
    for alias, canonical in _LABEL_TO_CANONICAL.items():
        if alias.replace(" ", "") == compact:
            return canonical
    # Already a canonical key
    snake = normalized.replace(" ", "_")
    if snake in PAYSLIP_FIELD_KEYS or snake == "national_id" or snake == "total_deductions":
        return snake
    return None


def _field_payload(value: Any, *, confidence: float | None, source_text: str | None) -> dict[str, Any]:
    empty = value is None or (isinstance(value, str) and not value.strip())
    status = FieldExtractionStatus.MISSING if empty else FieldExtractionStatus.FOUND
    return ExtractedField(
        value=None if empty else value,
        confidence=None if empty else confidence,
        source_text=source_text,
        status=status,
        edited_by_user=False,
        original_value=None,
    ).model_dump(mode="json")


def map_dynamic_entries_to_structured(
    entries: list[DynamicDocumentEntry],
) -> tuple[dict[str, Any], list[str]]:
    """Build canonical structured_data from confirmed dynamic entries.

    Unknown labels are preserved under additional_fields with their original key.
    First match wins for each canonical key.
    """
    structured: dict[str, Any] = {}
    additional: dict[str, Any] = {}
    warnings: list[str] = []
    seen_canonical: set[str] = set()

    for entry in entries:
        if not is_document_origin_entry(entry):
            continue
        label = entry.key.strip()
        canonical = resolve_canonical_key(label) if label else None
        payload = _field_payload(
            entry.value,
            confidence=entry.confidence,
            source_text=entry.source_text or (label or None),
        )

        if canonical and canonical in PAYSLIP_FIELD_KEYS:
            if canonical in seen_canonical:
                warnings.append(f"duplicate_canonical:{canonical}")
                continue
            seen_canonical.add(canonical)
            structured[canonical] = payload
        elif canonical == "national_id" or canonical == "total_deductions":
            additional[canonical] = payload
        else:
            # Keep document label for unmapped extras (including unlabeled values).
            display_label = label or "unknown"
            safe_key = (
                re.sub(r"[^\w\u0590-\u05FF\u0600-\u06FF]+", "_", display_label).strip("_") or "unknown"
            )
            if safe_key in additional:
                safe_key = f"{safe_key}_{entry.id[:8]}"
            additional[safe_key] = {
                **payload,
                "label": display_label,
            }
            if label:
                warnings.append(f"unmapped_label:{label}")
            else:
                warnings.append("unmapped_unlabeled_value")

    for key in PAYSLIP_FIELD_KEYS:
        if key not in structured:
            structured[key] = _field_payload(None, confidence=None, source_text=None)

    structured["additional_fields"] = additional
    return structured, list(dict.fromkeys(warnings))


# Reserved keys stored alongside canonical fields; never projected as review fields.
STRUCTURED_META_KEYS = frozenset(
    {"additional_fields", "parser_notes", "language", "dynamic_entries"}
)


def entries_from_structured(structured: dict[str, Any] | None) -> list[DynamicDocumentEntry]:
    """Load Document Model rows preserved inside structured_data."""
    if not isinstance(structured, dict):
        return []
    return entries_from_payload(structured.get("dynamic_entries"))


def project_structured_from_entries(
    entries: list[DynamicDocumentEntry],
) -> tuple[dict[str, Any], list[str]]:
    """Stage-2: map Document Model → Canonical while retaining full entries.

    Document Model remains the source of truth under ``dynamic_entries``.
    Canonical keys feed validation / identity matching only.
    """
    mapped, warnings = map_dynamic_entries_to_structured(entries)
    mapped["dynamic_entries"] = [entry.to_dict() for entry in entries]
    return mapped, warnings


def apply_corrections_to_entries(
    entries: list[DynamicDocumentEntry],
    corrections: list[tuple[str, Any, bool]],
) -> list[DynamicDocumentEntry]:
    """Apply (key, value, clear) corrections onto document-origin entries.

    Matching is by entry key (document label). Unknown keys append a user entry.
    """
    out = list(entries)
    for key, value, clear in corrections:
        label = (key or "").strip()
        if not label:
            continue
        matched = next((entry for entry in out if entry.key == label), None)
        if matched is None:
            if clear:
                continue
            out.append(
                new_entry(key=label, value=value, source="user", kind="field")
            )
            continue
        if clear:
            matched.value = None
            matched.source = "user"
        else:
            matched.value = value
            matched.source = "user"
    return out
