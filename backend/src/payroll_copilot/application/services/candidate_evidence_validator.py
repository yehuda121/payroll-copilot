"""Phase 3 candidate evidence validation + deterministic hydration.

Rejects hallucinated values and unknown candidate references.
Does not silently repair invalid model outputs by inventing evidence.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    PAYSLIP_FIELD_KEYS,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.parser_evidence import normalize_numeric_token


def hydrate_and_validate_candidate_fields(
    parsed: StructuredPayslipParse,
    *,
    candidate_index: dict[str, dict[str, Any]],
) -> StructuredPayslipParse:
    """Hydrate field provenance from candidates; reject unsupported mappings.

    Rules:
    - Non-null / FOUND|UNCERTAIN fields must cite known candidate_ids.
    - Value is taken from the first valid candidate (LLM value is not trusted).
    - Unknown candidate_id → clear field (MISSING) with warning.
    - Conflicted candidates → keep value as UNCERTAIN.
    - Missing evidence → MISSING / Unknown (never invent).
    """
    known_ids = set(candidate_index.keys())
    data = parsed.model_dump()

    for key in PAYSLIP_FIELD_KEYS:
        field = ExtractedField.model_validate(data[key])
        data[key] = _hydrate_one(field, candidate_index=candidate_index, known_ids=known_ids).model_dump()

    additional: dict[str, dict[str, Any]] = {}
    for name, raw in (parsed.additional_fields or {}).items():
        field = raw if isinstance(raw, ExtractedField) else ExtractedField.model_validate(raw)
        additional[name] = _hydrate_one(
            field, candidate_index=candidate_index, known_ids=known_ids
        ).model_dump()
    data["additional_fields"] = additional
    return StructuredPayslipParse.model_validate(data)


def _hydrate_one(
    field: ExtractedField,
    *,
    candidate_index: dict[str, dict[str, Any]],
    known_ids: set[str],
) -> ExtractedField:
    warnings = list(field.warnings or [])
    if field.edited_by_user:
        return field

    candidate_ids = [str(cid).strip() for cid in (field.candidate_ids or []) if str(cid).strip()]
    # Also accept a model that put a single id in evidence_ids by mistake when it
    # looks like a cand_* id — still require it to exist in the index.
    if not candidate_ids:
        for eid in field.evidence_ids or []:
            text = str(eid).strip()
            if text.startswith("cand_") and text in known_ids:
                candidate_ids.append(text)

    status = field.status
    wants_value = (
        status in {FieldExtractionStatus.FOUND, FieldExtractionStatus.UNCERTAIN}
        or field.value not in (None, "")
        or bool(candidate_ids)
    )

    if status == FieldExtractionStatus.MISSING and not candidate_ids:
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.MISSING,
            edited_by_user=False,
            original_value=field.original_value,
            evidence_ids=[],
            candidate_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method="evidence_bound_llm",
            warnings=warnings,
            normalized_value=None,
        )

    if not wants_value:
        return ExtractedField(
            value=None,
            confidence=None,
            source_text=None,
            status=FieldExtractionStatus.MISSING,
            edited_by_user=False,
            original_value=field.original_value,
            evidence_ids=[],
            candidate_ids=[],
            source_bbox=None,
            source_page=None,
            parser_method="evidence_bound_llm",
            warnings=warnings,
            normalized_value=None,
        )

    if not candidate_ids:
        warnings.append("missing_candidate_ids")
        return _cleared(warnings, original=field.original_value, reason="missing_candidate_ids")

    resolved: list[dict[str, Any]] = []
    for cid in candidate_ids:
        if cid not in known_ids:
            warnings.append(f"unknown_candidate_id:{cid}")
            continue
        resolved.append(candidate_index[cid])

    if not resolved:
        warnings.append("invalid_candidate_references")
        return _cleared(warnings, original=field.original_value, reason="invalid_candidate_references")

    primary = resolved[0]
    value_text = str(primary.get("value_text") or "").strip()
    if not value_text:
        warnings.append("empty_candidate_value")
        return _cleared(warnings, original=field.original_value, reason="empty_candidate_value")

    # Reject LLM-invented values: if the model supplied a value that does not
    # correspond to the candidate text, discard the model value and use candidate.
    model_value = field.value
    if model_value not in (None, "") and not _value_matches_candidate(model_value, value_text):
        warnings.append("hallucinated_value_rejected")
        # Continue with candidate text — do not keep the hallucinated value.

    hydrated_value: Any = value_text
    normalized = primary.get("normalized_value")
    if normalized is None:
        normalized = normalize_numeric_token(value_text)
    if normalized is not None and _looks_numeric_field_value(model_value, value_text):
        # Prefer numeric type when the evidence is numeric.
        hydrated_value = int(normalized) if float(normalized).is_integer() else float(normalized)

    conflict = any(bool(item.get("conflict")) for item in resolved)
    out_status = FieldExtractionStatus.UNCERTAIN if conflict else FieldExtractionStatus.FOUND
    if conflict:
        warnings.append("conflicted_candidate")

    confidence = _confidence_from_band(primary.get("confidence"))
    if conflict and confidence is not None:
        confidence = min(confidence, 0.59)

    return ExtractedField(
        value=hydrated_value,
        confidence=confidence,
        source_text=value_text,
        status=out_status,
        edited_by_user=False,
        original_value=field.original_value,
        evidence_ids=list(primary.get("source_line_ids") or [])[:8],
        candidate_ids=[str(item.get("candidate_id")) for item in resolved if item.get("candidate_id")],
        source_bbox=list(primary["bbox"]) if isinstance(primary.get("bbox"), list) else None,
        source_page=int(primary["page"]) if primary.get("page") is not None else None,
        parser_method="evidence_bound_llm",
        warnings=list(dict.fromkeys(warnings)),
        normalized_value=float(normalized) if normalized is not None else None,
    )


def _cleared(
    warnings: list[str],
    *,
    original: Any,
    reason: str,
) -> ExtractedField:
    return ExtractedField(
        value=None,
        confidence=None,
        source_text=None,
        status=FieldExtractionStatus.MISSING,
        edited_by_user=False,
        original_value=original,
        evidence_ids=[],
        candidate_ids=[],
        source_bbox=None,
        source_page=None,
        parser_method="evidence_bound_llm",
        warnings=list(dict.fromkeys([*warnings, reason])),
        normalized_value=None,
    )


def _value_matches_candidate(model_value: object, value_text: str) -> bool:
    if isinstance(model_value, (int, float)) and not isinstance(model_value, bool):
        candidate_num = normalize_numeric_token(value_text)
        if candidate_num is None:
            return False
        return abs(float(model_value) - candidate_num) < 1e-9
    if isinstance(model_value, str):
        if model_value.strip() == value_text.strip():
            return True
        left = normalize_numeric_token(model_value)
        right = normalize_numeric_token(value_text)
        if left is not None and right is not None:
            return abs(left - right) < 1e-9
        return value_text.strip() in model_value or model_value.strip() in value_text
    return False


def _looks_numeric_field_value(model_value: object, value_text: str) -> bool:
    if isinstance(model_value, (int, float)) and not isinstance(model_value, bool):
        return True
    return normalize_numeric_token(value_text) is not None


def _confidence_from_band(band: object) -> float | None:
    from payroll_copilot.application.services.confidence_normalize import (
        normalize_unit_interval_confidence,
    )

    return normalize_unit_interval_confidence(band)
