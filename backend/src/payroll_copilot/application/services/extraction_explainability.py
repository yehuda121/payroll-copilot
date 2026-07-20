"""Read-only Phase 4 explainability projection.

Consumes persisted structured_data and layout_analysis. It never reruns layout
analysis, association, evidence binding, parsing, or validation.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.confidence_normalize import (
    normalize_unit_interval_confidence,
)


def _normalize_association_confidence(value: object) -> object:
    """Keep band strings; coerce numeric 0–100 scales to unit interval."""
    if isinstance(value, str):
        band = value.strip().lower()
        if band in {"high", "medium", "low", "unknown"}:
            return band
    normalized = normalize_unit_interval_confidence(value)
    if normalized is not None:
        return normalized
    return value if value not in (None, "") else "unknown"


def build_field_evidence_map(
    structured_data: dict[str, Any] | None,
    layout_analysis: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Project internal candidate data into a stable, presentation-safe DTO."""
    structured = structured_data or {}
    analysis = layout_analysis or {}
    associations = {
        str(item.get("id")): item
        for item in (analysis.get("associations") or [])
        if isinstance(item, dict) and item.get("id")
    }
    cells: dict[str, dict[str, Any]] = {}
    rows: dict[str, dict[str, Any]] = {}
    for page in analysis.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for cell in page.get("cells") or []:
            if isinstance(cell, dict) and cell.get("id"):
                cells[str(cell["id"])] = cell
        for row in page.get("rows") or []:
            if isinstance(row, dict) and row.get("id"):
                rows[str(row["id"])] = row

    evidence: dict[str, dict[str, Any]] = {}
    for key, payload in _iter_fields(structured):
        if not isinstance(payload, dict):
            evidence[key] = {
                "available": False,
                "reason": "candidate_reference_unavailable",
                "candidate_id": None,
                "alternatives": [],
            }
            continue
        candidate_ids = [
            str(value)
            for value in (payload.get("candidate_ids") or [])
            if value
        ]
        user_edited = bool(payload.get("edited_by_user"))
        if not candidate_ids:
            evidence[key] = {
                "available": False,
                "reason": (
                    "user_edited"
                    if user_edited
                    else "candidate_reference_unavailable"
                ),
                "candidate_id": None,
                "user_edited": user_edited,
                "alternatives": [],
            }
            continue
        primary = _candidate_details(
            candidate_ids[0],
            associations=associations,
            cells=cells,
            rows=rows,
        )
        if primary is None:
            evidence[key] = {
                "available": False,
                "reason": (
                    "user_edited"
                    if user_edited
                    else "candidate_reference_unavailable"
                ),
                "candidate_id": candidate_ids[0],
                "user_edited": user_edited,
                "alternatives": [],
            }
            continue
        # Corrected values remain human-authoritative. Geometry describes the
        # original extraction only and never re-validates the edited value.
        primary["available"] = not user_edited
        primary["user_edited"] = user_edited
        if user_edited:
            primary["reason"] = "user_edited"
        primary["alternatives"] = _alternatives(
            primary,
            associations=associations,
            cells=cells,
            rows=rows,
        )
        evidence[key] = primary
    return evidence


def attach_field_evidence(
    fields: list[dict[str, Any]],
    evidence_by_field: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return additive field DTOs; existing keys and values remain unchanged."""
    return [
        {
            **field,
            "evidence_details": evidence_by_field.get(str(field.get("key") or "")),
        }
        for field in fields
    ]


def build_validation_explanation(
    *,
    finding: Any,
    structured_data: dict[str, Any] | None,
    evidence_by_field: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Trace one validation finding to deterministic extracted evidence."""
    key = _finding_field_key(finding, structured_data or {})
    details = evidence_by_field.get(key) if key else None
    severity = _enum_value(getattr(finding, "severity", None))
    if details and details.get("user_edited"):
        return {
            "available": False,
            "result": _validation_result(severity),
            "reason": "user_edited",
            "field_key": key,
        }
    if details and details.get("available"):
        reason = (
            "conflicting_extraction_evidence"
            if details.get("conflict")
            else "validation_based_on_extracted_evidence"
        )
        return {
            "available": True,
            "result": _validation_result(severity),
            "reason": reason,
            "field_key": key,
            "candidate_id": details.get("candidate_id"),
            "page": details.get("page"),
            "label": details.get("label"),
            "value": details.get("value"),
            "association_strategy": details.get("association_strategy"),
            "association_confidence": details.get("association_confidence"),
            "conflict": bool(details.get("conflict")),
        }
    return {
        "available": False,
        "result": _validation_result(severity),
        "reason": "extraction_evidence_unavailable",
        "field_key": key,
    }


def build_validation_run_explanation(
    *,
    overall_result: Any,
    fields: list[dict[str, Any]],
    evidence_by_field: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Explain a run outcome without changing or re-evaluating validation."""
    supported = sum(
        1
        for field in fields
        if (evidence_by_field.get(str(field.get("key") or "")) or {}).get("available")
    )
    extracted = sum(1 for field in fields if field.get("value") not in (None, ""))
    return {
        "result": _enum_value(overall_result) or None,
        "reason": (
            "validation_completed_with_traceable_evidence"
            if supported
            else "validation_completed_without_traceable_evidence"
        ),
        "extracted_field_count": extracted,
        "evidence_supported_field_count": supported,
    }


def build_assistant_evidence_context(
    structured_data: dict[str, Any] | None,
    layout_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Small facts-only context. Missing evidence is explicit."""
    evidence = build_field_evidence_map(structured_data, layout_analysis)
    rows: list[dict[str, Any]] = []
    for key, payload in _iter_fields(structured_data or {}):
        value = payload.get("value") if isinstance(payload, dict) else payload
        if value in (None, ""):
            continue
        details = evidence.get(key)
        if not details or not details.get("available"):
            rows.append({"field": key, "evidence_available": False})
            continue
        rows.append(
            {
                "field": key,
                "evidence_available": True,
                "candidate_id": details.get("candidate_id"),
                "page": details.get("page"),
                "section": details.get("section"),
                "row": details.get("row"),
                "label": details.get("label"),
                "value": details.get("value"),
                "association_strategy": details.get("association_strategy"),
                "association_confidence": details.get("association_confidence"),
                "conflict": bool(details.get("conflict")),
                "alternative_count": len(details.get("alternatives") or []),
            }
        )
    return rows


def _candidate_details(
    candidate_id: str,
    *,
    associations: dict[str, dict[str, Any]],
    cells: dict[str, dict[str, Any]],
    rows: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if candidate_id.startswith("cand_unresolved_"):
        value_id = candidate_id[len("cand_unresolved_") :]
        value_cell = cells.get(value_id)
        if value_cell is None:
            return None
        row_id = str(value_cell.get("row_id") or "")
        row = rows.get(row_id, {})
        return {
            "candidate_id": candidate_id,
            "source": "layout_analysis",
            "page": int(_page_from_id(row_id) or 1),
            "section": row.get("section_id"),
            "row": row_id or None,
            "column": value_cell.get("column_index"),
            "label": None,
            "value": value_cell.get("text"),
            "association_strategy": "unresolved_value",
            "association_confidence": _normalize_association_confidence(
                value_cell.get("confidence") or "unknown"
            ),
            "bbox": (
                list(value_cell["bbox"])
                if isinstance(value_cell.get("bbox"), list)
                else None
            ),
            "conflict": False,
            "conflict_group": None,
            "source_line_ids": list(value_cell.get("source_line_ids") or []),
            "source_word_ids": list(value_cell.get("source_word_ids") or []),
            "_association_id": "",
        }
    parsed = _parse_candidate_id(candidate_id)
    if parsed is None:
        return None
    association_id, alternative_index = parsed
    association = associations.get(association_id)
    if association is None:
        return None
    candidate = association
    if alternative_index is not None:
        alternatives = association.get("alternatives") or []
        if alternative_index >= len(alternatives):
            return None
        alternative = alternatives[alternative_index]
        if not isinstance(alternative, dict):
            return None
        candidate = {**association, **alternative, "conflict": True}

    value_id = str(candidate.get("value_id") or "")
    label_id = str(association.get("label_id") or "")
    value_cell = cells.get(value_id, {})
    label_cell = cells.get(label_id, {})
    row_id = str(
        value_cell.get("row_id")
        or label_cell.get("row_id")
        or (candidate.get("evidence") or {}).get("value_row_id")
        or ""
    )
    row = rows.get(row_id, {})
    bbox = value_cell.get("bbox")
    if not isinstance(bbox, list):
        raw = (candidate.get("evidence") or {}).get("value_bbox")
        bbox = list(raw) if isinstance(raw, list) else None
    return {
        "candidate_id": candidate_id,
        "source": "layout_analysis",
        "page": int(candidate.get("page") or _page_from_id(row_id) or 1),
        "section": row.get("section_id"),
        "row": row_id or None,
        "column": value_cell.get("column_index"),
        "label": association.get("label_text"),
        "value": candidate.get("value_text"),
        "association_strategy": candidate.get("relation"),
        "association_confidence": _normalize_association_confidence(
            candidate.get("confidence")
        ),
        "bbox": bbox,
        "conflict": bool(candidate.get("conflict") or association.get("conflict")),
        "conflict_group": association.get("conflict_group"),
        "source_line_ids": list(value_cell.get("source_line_ids") or []),
        "source_word_ids": list(value_cell.get("source_word_ids") or []),
        "_association_id": association_id,
    }


def _alternatives(
    primary: dict[str, Any],
    *,
    associations: dict[str, dict[str, Any]],
    cells: dict[str, dict[str, Any]],
    rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    association_id = str(primary.get("_association_id") or "")
    association = associations.get(association_id) or {}
    output: list[dict[str, Any]] = []
    parsed = _parse_candidate_id(str(primary.get("candidate_id") or ""))
    selected_alternative = parsed[1] if parsed is not None else None
    if selected_alternative is not None:
        details = _candidate_details(
            f"cand_{association_id}",
            associations=associations,
            cells=cells,
            rows=rows,
        )
        if details is not None:
            details.pop("_association_id", None)
            details["reason"] = "association_engine_primary_not_selected"
            output.append(details)
    for index, _ in enumerate(association.get("alternatives") or []):
        if index == selected_alternative:
            continue
        details = _candidate_details(
            f"cand_{association_id}_alt{index}",
            associations=associations,
            cells=cells,
            rows=rows,
        )
        if details is not None:
            details.pop("_association_id", None)
            details["reason"] = "association_engine_alternative"
            output.append(details)
    primary.pop("_association_id", None)
    return output


def _parse_candidate_id(candidate_id: str) -> tuple[str, int | None] | None:
    if not candidate_id.startswith("cand_"):
        return None
    value = candidate_id[5:]
    if "_alt" not in value:
        return value, None
    association_id, raw_index = value.rsplit("_alt", 1)
    try:
        return association_id, int(raw_index)
    except ValueError:
        return None


def _finding_field_key(finding: Any, structured: dict[str, Any]) -> str | None:
    """Resolve a finding to a field only via explicit deterministic keys.

    Actual-value matching is intentionally avoided: dense payslips can contain
    duplicate amounts and would invent incorrect evidence bindings.
    """
    params = dict(getattr(finding, "message_params", None) or {})
    known = {key for key, _ in _iter_fields(structured)}
    for name in ("field", "field_key", "key"):
        value = params.get(name)
        if isinstance(value, str) and value in known:
            return value
    return None


def _iter_fields(structured: dict[str, Any]):
    for key, payload in structured.items():
        if key in {"additional_fields", "parser_notes", "language"}:
            continue
        yield str(key), payload
    additional = structured.get("additional_fields")
    if isinstance(additional, dict):
        for key, payload in additional.items():
            yield str(key), payload


def _validation_result(severity: str) -> str:
    if severity in {"critical", "error", "failed"}:
        return "failed"
    if severity in {"warning", "uncertain"}:
        return "uncertain"
    return "passed"


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value.value if hasattr(value, "value") else value)


def _page_from_id(value: str) -> int | None:
    if not value.startswith("p"):
        return None
    try:
        return int(value[1:].split("_", 1)[0])
    except ValueError:
        return None
