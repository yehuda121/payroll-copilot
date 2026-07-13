"""Post-process parser fields: never invent confidence; justify via source_text."""

from __future__ import annotations

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).casefold()


def source_appears_in_ocr(source_text: str | None, ocr_text: str) -> bool:
    if not source_text or not source_text.strip():
        return False
    if not ocr_text or not ocr_text.strip():
        return False
    haystack = _normalize_whitespace(ocr_text)
    needle = _normalize_whitespace(source_text)
    if not needle:
        return False
    if needle in haystack:
        return True
    # Allow compact numeric/code matches without spaces (common OCR noise).
    compact_hay = haystack.replace(" ", "")
    compact_needle = needle.replace(" ", "")
    return bool(compact_needle) and compact_needle in compact_hay


def sanitize_field(field: ExtractedField, *, ocr_text: str) -> ExtractedField:
    """Apply honesty rules to one field.

    Confidence rules:
    - Keep confidence only when in [0,1] AND status is FOUND|UNCERTAIN AND
      source_text is present and appears in OCR text.
    - Otherwise confidence → null.
    """
    status = field.status
    value = field.value
    source_text = field.source_text.strip() if isinstance(field.source_text, str) else field.source_text
    if source_text == "":
        source_text = None

    confidence = field.confidence
    if confidence is not None and (confidence < 0.0 or confidence > 1.0):
        confidence = None

    justified = source_appears_in_ocr(source_text, ocr_text)

    if status == FieldExtractionStatus.MISSING:
        return ExtractedField(
            value=None if value in ("", None) else value,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.MISSING,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method,
            warnings=list(field.warnings or []),
            normalized_value=None,
        )

    if status == FieldExtractionStatus.FOUND and (value is None or value == ""):
        status = FieldExtractionStatus.UNCERTAIN

    if confidence is not None and not justified:
        confidence = None

    if status == FieldExtractionStatus.FOUND and not justified:
        # Value claimed FOUND without usable OCR evidence → downgrade honesty.
        status = FieldExtractionStatus.UNCERTAIN
        confidence = None

    return ExtractedField(
        value=value,
        confidence=confidence,
        source_text=source_text,
        status=status,
        edited_by_user=field.edited_by_user,
        original_value=field.original_value,
        evidence_ids=list(field.evidence_ids or []),
        source_bbox=field.source_bbox,
        source_page=field.source_page,
        parser_method=field.parser_method,
        warnings=list(field.warnings or []),
        normalized_value=field.normalized_value,
    )


def sanitize_structured_payslip(
    parsed: StructuredPayslipParse,
    *,
    ocr_text: str,
) -> StructuredPayslipParse:
    data = parsed.model_dump()
    for key in list(data.keys()):
        if key in {"additional_fields", "parser_notes", "language"}:
            continue
        data[key] = sanitize_field(ExtractedField.model_validate(data[key]), ocr_text=ocr_text).model_dump()

    additional: dict[str, dict] = {}
    for name, field_data in (parsed.additional_fields or {}).items():
        additional[name] = sanitize_field(
            field_data if isinstance(field_data, ExtractedField) else ExtractedField.model_validate(field_data),
            ocr_text=ocr_text,
        ).model_dump()
    data["additional_fields"] = additional
    return StructuredPayslipParse.model_validate(data)
