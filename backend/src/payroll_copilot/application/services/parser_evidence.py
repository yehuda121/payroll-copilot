"""Deterministic evidence validation for layout-aware payslip parser output."""

from __future__ import annotations

import re
from typing import Any

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.payslip_field_sanitizer import source_appears_in_ocr

_EVIDENCE_ID_RE = re.compile(r"^p\d+_l\d+(?:_w\d+)?$")
_MONEY_RE = re.compile(
    r"^\s*[-+]?\s*(?:₪|NIS|ILS|\$|€|£)?\s*(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d+))?\s*$"
)


def is_valid_evidence_id(evidence_id: str) -> bool:
    return bool(_EVIDENCE_ID_RE.match(evidence_id.strip()))


def normalize_numeric_token(text: str) -> float | None:
    """Normalize OCR money/number text without inventing digits."""
    if not text or not str(text).strip():
        return None
    raw = str(text).strip().replace("\u200f", "").replace("\u200e", "")
    raw = raw.replace(" ", "")
    match = _MONEY_RE.match(raw)
    if not match:
        # Try stripping trailing punctuation commonly attached by OCR.
        trimmed = raw.strip("]).,;:")
        match = _MONEY_RE.match(trimmed)
        if not match:
            return None
    whole = match.group(1).replace(",", "")
    frac = match.group(2)
    try:
        if frac is None:
            return float(whole)
        return float(f"{whole}.{frac}")
    except ValueError:
        return None


def _values_correspond(value: object, source_text: str | None) -> bool:
    if source_text is None:
        return False
    if value is None:
        return False
    if isinstance(value, bool):
        return str(value).casefold() in source_text.casefold()
    if isinstance(value, (int, float)):
        source_num = normalize_numeric_token(source_text)
        if source_num is None:
            return False
        return abs(float(value) - source_num) < 1e-9
    if isinstance(value, str):
        # Exact or whitespace-normalized containment either direction.
        if value.strip() == source_text.strip():
            return True
        left = normalize_numeric_token(value)
        right = normalize_numeric_token(source_text)
        if left is not None and right is not None:
            return abs(left - right) < 1e-9
        return source_appears_in_ocr(value, source_text) or source_appears_in_ocr(source_text, value)
    return False


def _bbox_compatible(
    claimed: list[float] | tuple[float, ...] | None,
    evidence_boxes: list[list[float]],
) -> bool:
    if claimed is None:
        return True
    if len(claimed) != 4:
        return False
    try:
        cx, cy, cw, ch = (float(v) for v in claimed)
    except (TypeError, ValueError):
        return False
    if cw <= 0 or ch <= 0:
        return False
    if not evidence_boxes:
        return False
    # Accept exact match or claimed box that equals/covers any evidence box within 1px.
    for box in evidence_boxes:
        if len(box) != 4:
            continue
        ex, ey, ew, eh = box
        if (
            abs(cx - ex) <= 1.0
            and abs(cy - ey) <= 1.0
            and abs(cw - ew) <= 1.0
            and abs(ch - eh) <= 1.0
        ):
            return True
        # Claimed encloses evidence
        if cx <= ex + 1 and cy <= ey + 1 and cx + cw >= ex + ew - 1 and cy + ch >= ey + eh - 1:
            return True
    return False


def _evidence_texts_and_boxes(
    evidence_ids: list[str],
    evidence_index: dict[str, dict[str, Any]],
) -> tuple[list[str], list[list[float]], list[int], list[float]]:
    texts: list[str] = []
    boxes: list[list[float]] = []
    pages: list[int] = []
    confidences: list[float] = []
    for eid in evidence_ids:
        item = evidence_index.get(eid)
        if not item:
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
        bbox = item.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            boxes.append([float(v) for v in bbox])
        page = item.get("page")
        if isinstance(page, int):
            pages.append(page)
        conf = item.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(float(conf))
    return texts, boxes, pages, confidences


def validate_extracted_field_evidence(
    field: ExtractedField,
    *,
    evidence_index: dict[str, dict[str, Any]],
    ocr_text: str,
) -> ExtractedField:
    """Validate evidence-bound fields; never invent replacements."""
    warnings = list(field.warnings or [])

    if field.status == FieldExtractionStatus.MISSING:
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.MISSING,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method,
            warnings=warnings,
            normalized_value=None,
        )

    if field.value in (None, "") and field.status != FieldExtractionStatus.MISSING:
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "empty_value_without_missing_status"],
            normalized_value=None,
        )

    evidence_ids = [eid for eid in (field.evidence_ids or []) if isinstance(eid, str) and eid.strip()]
    if field.value not in (None, "") and not evidence_ids:
        # Non-null without evidence → unable to accept.
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "missing_evidence_ids"],
            normalized_value=None,
        )

    for eid in evidence_ids:
        if not is_valid_evidence_id(eid) or eid not in evidence_index:
            return ExtractedField(
                value=None,
                confidence=None,
                source_text=None,
                status=FieldExtractionStatus.UNCERTAIN,
                edited_by_user=field.edited_by_user,
                original_value=field.original_value,
                evidence_ids=[],
                source_bbox=None,
                source_page=None,
                parser_method=field.parser_method or "layout_llm",
                warnings=[*warnings, f"unknown_or_invalid_evidence_id:{eid}"],
                normalized_value=None,
            )

    texts, boxes, pages, confidences = _evidence_texts_and_boxes(evidence_ids, evidence_index)
    joined_evidence = " ".join(texts)
    source_text = field.source_text.strip() if isinstance(field.source_text, str) else None
    if source_text == "":
        source_text = None

    if source_text is None or not (
        source_appears_in_ocr(source_text, joined_evidence)
        or any(source_appears_in_ocr(source_text, t) for t in texts)
        or source_appears_in_ocr(source_text, ocr_text)
    ):
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "source_text_not_in_evidence"],
            normalized_value=None,
        )

    if not _values_correspond(field.value, source_text):
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "value_not_supported_by_source_text"],
            normalized_value=None,
        )

    # Reject digit invention: numeric value digits must come from source_text.
    if isinstance(field.value, (int, float)):
        source_num = normalize_numeric_token(source_text)
        if source_num is None or abs(float(field.value) - source_num) >= 1e-9:
            return ExtractedField(
                value=None,
                confidence=None,
                source_text=None,
                status=FieldExtractionStatus.UNCERTAIN,
                edited_by_user=field.edited_by_user,
                original_value=field.original_value,
                evidence_ids=[],
                source_bbox=None,
                source_page=None,
                parser_method=field.parser_method or "layout_llm",
                warnings=[*warnings, "numeric_value_mismatches_evidence"],
                normalized_value=None,
            )

    if field.source_bbox is not None and not _bbox_compatible(field.source_bbox, boxes):
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "source_bbox_mismatch"],
            normalized_value=None,
        )

    source_page = field.source_page
    if source_page is not None and pages and source_page not in pages:
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.UNCERTAIN,
            edited_by_user=field.edited_by_user,
            original_value=field.original_value,
            evidence_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method=field.parser_method or "layout_llm",
            warnings=[*warnings, "source_page_mismatch"],
            normalized_value=None,
        )

    max_ocr_conf = max(confidences) if confidences else None
    confidence = field.confidence
    if confidence is not None and (confidence < 0.0 or confidence > 1.0):
        confidence = None
    if confidence is not None and max_ocr_conf is not None and confidence > max_ocr_conf + 1e-9:
        # Cap to supporting OCR evidence confidence.
        confidence = max_ocr_conf
        warnings.append("confidence_capped_to_ocr_evidence")

    normalized_value = field.normalized_value
    if normalized_value is None and isinstance(field.value, (int, float)):
        normalized_value = float(field.value)
    elif normalized_value is None and isinstance(source_text, str):
        normalized_value = normalize_numeric_token(source_text)

    if normalized_value is not None and source_text is not None:
        source_num = normalize_numeric_token(source_text)
        if source_num is not None and abs(float(normalized_value) - source_num) >= 1e-9:
            warnings.append("normalized_value_cleared_mismatch")
            normalized_value = None

    status = field.status
    if status == FieldExtractionStatus.FOUND and confidence is not None and confidence < 0.5:
        status = FieldExtractionStatus.UNCERTAIN

    return ExtractedField(
        value=field.value,
        confidence=confidence,
        source_text=source_text,
        status=status,
        edited_by_user=field.edited_by_user,
        original_value=field.original_value,
        evidence_ids=evidence_ids,
        source_bbox=list(field.source_bbox) if field.source_bbox is not None else None,
        source_page=source_page if source_page is not None else (pages[0] if pages else None),
        parser_method=field.parser_method or "layout_llm",
        warnings=warnings,
        normalized_value=normalized_value,
    )


def apply_plausibility_checks(parsed: StructuredPayslipParse) -> StructuredPayslipParse:
    """Non-corrective sanity checks — may lower confidence or mark uncertain."""
    data = parsed.model_dump()

    def _money(field_key: str) -> float | None:
        field = ExtractedField.model_validate(data[field_key])
        if field.normalized_value is not None:
            return float(field.normalized_value)
        if isinstance(field.value, (int, float)):
            return float(field.value)
        if isinstance(field.value, str):
            return normalize_numeric_token(field.value)
        return None

    gross = _money("gross_salary")
    net = _money("net_salary")
    if gross is not None and net is not None and net > gross + 1e-6:
        field = ExtractedField.model_validate(data["net_salary"])
        warnings = list(field.warnings or [])
        warnings.append("net_exceeds_gross")
        data["net_salary"] = field.model_copy(
            update={
                "status": FieldExtractionStatus.UNCERTAIN,
                "confidence": min(field.confidence or 0.0, 0.4) if field.confidence is not None else None,
                "warnings": warnings,
            }
        ).model_dump()

    for money_key in (
        "base_salary",
        "travel_expenses",
        "gross_salary",
        "net_salary",
        "income_tax",
        "national_insurance",
        "health_tax",
        "pension_employee",
        "pension_employer",
    ):
        amount = _money(money_key)
        if amount is not None and amount < 0:
            field = ExtractedField.model_validate(data[money_key])
            warnings = list(field.warnings or [])
            warnings.append("negative_money_flagged")
            data[money_key] = field.model_copy(
                update={"status": FieldExtractionStatus.UNCERTAIN, "warnings": warnings}
            ).model_dump()

    return StructuredPayslipParse.model_validate(data)


def validate_structured_payslip_evidence(
    parsed: StructuredPayslipParse,
    *,
    evidence_index: dict[str, dict[str, Any]],
    ocr_text: str,
) -> StructuredPayslipParse:
    data = parsed.model_dump()
    for key, value in list(data.items()):
        if key in {"additional_fields", "parser_notes", "language"}:
            continue
        data[key] = validate_extracted_field_evidence(
            ExtractedField.model_validate(value),
            evidence_index=evidence_index,
            ocr_text=ocr_text,
        ).model_dump()

    additional: dict[str, dict[str, Any]] = {}
    for name, field_data in (parsed.additional_fields or {}).items():
        additional[name] = validate_extracted_field_evidence(
            field_data if isinstance(field_data, ExtractedField) else ExtractedField.model_validate(field_data),
            evidence_index=evidence_index,
            ocr_text=ocr_text,
        ).model_dump()
    data["additional_fields"] = additional
    validated = StructuredPayslipParse.model_validate(data)
    return apply_plausibility_checks(validated)
