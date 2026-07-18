"""Phase 3 Evidence Binder — deterministic candidates from layout_analysis.

No AI. No payroll mapping. Builds the evidence package the LLM may consume.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.parser_evidence import normalize_numeric_token

EVIDENCE_BUNDLE_SCHEMA_VERSION = 1


def bind_evidence_candidates(
    layout_analysis: dict[str, Any] | None,
    *,
    max_candidates: int = 400,
) -> dict[str, Any]:
    """Collect association-backed candidates with full geometric provenance.

    Each candidate is addressable by ``candidate_id`` and carries label/value
    text, page/row/column/section, bbox, confidence, and association strategy.
    """
    if not layout_analysis or not isinstance(layout_analysis, dict):
        return _empty_bundle(warning="evidence_binder_missing_layout_analysis")

    pages = {
        int(page.get("page") or 0): page
        for page in (layout_analysis.get("pages") or [])
        if isinstance(page, dict)
    }
    cells_by_id: dict[str, dict[str, Any]] = {}
    rows_by_id: dict[str, dict[str, Any]] = {}
    for page in pages.values():
        for cell in page.get("cells") or []:
            if isinstance(cell, dict) and cell.get("id"):
                cells_by_id[str(cell["id"])] = cell
        for row in page.get("rows") or []:
            if isinstance(row, dict) and row.get("id"):
                rows_by_id[str(row["id"])] = row

    candidates: list[dict[str, Any]] = []
    warnings: list[str] = list(layout_analysis.get("warnings") or [])

    for assoc in layout_analysis.get("associations") or []:
        if not isinstance(assoc, dict):
            continue
        if len(candidates) >= max_candidates:
            warnings.append("evidence_binder_candidates_truncated")
            break
        candidate = _candidate_from_association(
            assoc,
            cells_by_id=cells_by_id,
            rows_by_id=rows_by_id,
            alt=False,
            alt_index=None,
        )
        if candidate is not None:
            candidates.append(candidate)

        # Preserve alternatives as separate addressable candidates (never silent drop).
        for alt_index, alt in enumerate(assoc.get("alternatives") or []):
            if not isinstance(alt, dict):
                continue
            if len(candidates) >= max_candidates:
                warnings.append("evidence_binder_candidates_truncated")
                break
            alt_assoc = {
                **assoc,
                "value_id": alt.get("value_id"),
                "value_text": alt.get("value_text"),
                "relation": alt.get("relation") or assoc.get("relation"),
                "confidence": alt.get("confidence") or assoc.get("confidence"),
                "score": alt.get("score"),
                "conflict": True,
            }
            alt_candidate = _candidate_from_association(
                alt_assoc,
                cells_by_id=cells_by_id,
                rows_by_id=rows_by_id,
                alt=True,
                alt_index=alt_index,
            )
            if alt_candidate is not None:
                candidates.append(alt_candidate)

    # Unlabeled values remain available as evidence without inventing labels.
    for value_id in layout_analysis.get("unresolved_values") or []:
        if len(candidates) >= max_candidates:
            warnings.append("evidence_binder_candidates_truncated")
            break
        cell = cells_by_id.get(str(value_id))
        if not cell:
            continue
        text = str(cell.get("text") or "").strip()
        if not text:
            continue
        row = rows_by_id.get(str(cell.get("row_id") or ""))
        page_number = _page_from_row_id(str(cell.get("row_id") or "")) or 1
        candidate_id = f"cand_unresolved_{value_id}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "label_text": None,
                "value_text": text,
                "page": page_number,
                "section_id": (row or {}).get("section_id"),
                "row_id": cell.get("row_id"),
                "column_index": cell.get("column_index"),
                "bbox": list(cell["bbox"]) if isinstance(cell.get("bbox"), list) else None,
                "confidence": cell.get("confidence") or "unknown",
                "relation": "unresolved_value",
                "association_id": None,
                "label_cell_id": None,
                "value_cell_id": str(value_id),
                "source_line_ids": list(cell.get("source_line_ids") or []),
                "source_word_ids": list(cell.get("source_word_ids") or []),
                "conflict": False,
                "normalized_value": normalize_numeric_token(text),
            }
        )

    index = {str(item["candidate_id"]): item for item in candidates if item.get("candidate_id")}
    llm_view = [_llm_candidate_view(item) for item in candidates]

    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "binder": "evidence_binder_v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "candidate_index": index,
        "llm_candidates": llm_view,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _candidate_from_association(
    assoc: dict[str, Any],
    *,
    cells_by_id: dict[str, dict[str, Any]],
    rows_by_id: dict[str, dict[str, Any]],
    alt: bool,
    alt_index: int | None,
) -> dict[str, Any] | None:
    assoc_id = str(assoc.get("id") or "unknown")
    value_id = str(assoc.get("value_id") or "")
    label_id = str(assoc.get("label_id") or "")
    value_text = str(assoc.get("value_text") or "").strip()
    label_text = str(assoc.get("label_text") or "").strip() or None
    if not value_text:
        return None

    value_cell = cells_by_id.get(value_id)
    label_cell = cells_by_id.get(label_id)
    row = rows_by_id.get(str((value_cell or {}).get("row_id") or (label_cell or {}).get("row_id") or ""))
    evidence = assoc.get("evidence") if isinstance(assoc.get("evidence"), dict) else {}
    bbox = None
    if value_cell and isinstance(value_cell.get("bbox"), list):
        bbox = list(value_cell["bbox"])
    elif isinstance(evidence.get("value_bbox"), list):
        bbox = list(evidence["value_bbox"])

    page = int(assoc.get("page") or _page_from_row_id(str((value_cell or {}).get("row_id") or "")) or 1)
    suffix = f"_alt{alt_index}" if alt and alt_index is not None else ""
    candidate_id = f"cand_{assoc_id}{suffix}"

    source_line_ids: list[str] = []
    source_word_ids: list[str] = []
    for cell in (label_cell, value_cell):
        if not cell:
            continue
        source_line_ids.extend(str(x) for x in (cell.get("source_line_ids") or []) if x)
        source_word_ids.extend(str(x) for x in (cell.get("source_word_ids") or []) if x)

    return {
        "candidate_id": candidate_id,
        "label_text": label_text,
        "value_text": value_text,
        "page": page,
        "section_id": (row or {}).get("section_id"),
        "row_id": (value_cell or {}).get("row_id") or (label_cell or {}).get("row_id"),
        "column_index": (value_cell or {}).get("column_index"),
        "bbox": bbox,
        "confidence": assoc.get("confidence") or "unknown",
        "relation": assoc.get("relation") or "unknown",
        "association_id": assoc_id,
        "label_cell_id": label_id or None,
        "value_cell_id": value_id or None,
        "source_line_ids": list(dict.fromkeys(source_line_ids)),
        "source_word_ids": list(dict.fromkeys(source_word_ids)),
        "conflict": bool(assoc.get("conflict")) or alt,
        "score": assoc.get("score"),
        "normalized_value": normalize_numeric_token(value_text),
    }


def _llm_candidate_view(candidate: dict[str, Any]) -> dict[str, Any]:
    """Compact view for the prompt — enough for semantic mapping, no OCR dump."""
    return {
        "candidate_id": candidate.get("candidate_id"),
        "label": candidate.get("label_text"),
        "value": candidate.get("value_text"),
        "page": candidate.get("page"),
        "section_id": candidate.get("section_id"),
        "row_id": candidate.get("row_id"),
        "column_index": candidate.get("column_index"),
        "bbox": candidate.get("bbox"),
        "confidence": candidate.get("confidence"),
        "relation": candidate.get("relation"),
        "conflict": bool(candidate.get("conflict")),
    }


def _page_from_row_id(row_id: str) -> int | None:
    # row ids look like p1_r0
    if not row_id.startswith("p"):
        return None
    try:
        return int(row_id[1:].split("_", 1)[0])
    except ValueError:
        return None


def _empty_bundle(*, warning: str | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "binder": "evidence_binder_v1",
        "candidate_count": 0,
        "candidates": [],
        "candidate_index": {},
        "llm_candidates": [],
        "warnings": [],
    }
    if warning:
        payload["warnings"] = [warning]
    return payload
