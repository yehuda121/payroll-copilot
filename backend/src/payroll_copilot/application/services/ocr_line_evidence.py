"""OCR-line evidence candidates when layout analysis is unavailable.

Compact addressable values so semantic_v1 can still ground unlabeled header text.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.parser_evidence import (
    employee_name_implausible_reason,
    normalize_numeric_token,
)

# When layout saturates the merge budget, keep a bounded slice for high-priority
# unlabeled OCR lines (e.g. person-name headers) so prompt compaction can still see them.
DEFAULT_MERGE_MAX_CANDIDATES = 400
DEFAULT_HIGH_PRIORITY_OCR_RESERVE = 40


def evidence_candidate_priority_tier(item: dict[str, Any]) -> int:
    """Lower = higher priority. Shared by merge reservation and prompt compaction.

    Tier 0: unlabeled letter-bearing OCR / unresolved values (header names).
    Tier 1: other plausible person-name-like values.
    Tier 2: plausible values with a label.
    Tier 3: everything else (including implausible OCR digit/NID lines).
    """
    label = str(item.get("label") or item.get("label_text") or "").strip()
    value = str(item.get("value") or item.get("value_text") or "").strip()
    relation = str(item.get("relation") or "")
    if not value:
        return 3
    if employee_name_implausible_reason(value) is None and not label:
        if relation.startswith("ocr") or relation in {"unresolved_value", "unlabeled_value"}:
            return 0
        return 1
    if employee_name_implausible_reason(value) is None:
        return 2
    return 3


def build_ocr_line_evidence_bundle(
    *,
    ocr_text: str,
    pages_text: list[str] | None = None,
    ocr_pages: list[dict[str, Any]] | None = None,
    max_candidates: int = 250,
) -> dict[str, Any]:
    """Build candidate_id → line/value evidence from OCR pages or flat text."""
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []

    if ocr_pages:
        for page in ocr_pages:
            if not isinstance(page, dict):
                continue
            page_no = int(page.get("page") or 1)
            lines = page.get("lines") or []
            if lines:
                for idx, line in enumerate(lines):
                    if len(candidates) >= max_candidates:
                        warnings.append("ocr_line_candidates_truncated")
                        break
                    text = ""
                    bbox = None
                    conf: Any = None
                    if isinstance(line, dict):
                        text = str(line.get("text") or "").strip()
                        if isinstance(line.get("bbox"), list):
                            bbox = list(line["bbox"])
                        conf = line.get("confidence")
                    else:
                        text = str(line or "").strip()
                    if not text:
                        continue
                    candidates.append(
                        _candidate(
                            candidate_id=f"ocr_p{page_no}_l{idx}",
                            value_text=text,
                            page=page_no,
                            bbox=bbox,
                            confidence=conf,
                            relation="ocr_line",
                        )
                    )
            else:
                text = str(page.get("text") or "").strip()
                for idx, line_text in enumerate(_split_lines(text)):
                    if len(candidates) >= max_candidates:
                        warnings.append("ocr_line_candidates_truncated")
                        break
                    candidates.append(
                        _candidate(
                            candidate_id=f"ocr_p{page_no}_t{idx}",
                            value_text=line_text,
                            page=page_no,
                            bbox=None,
                            confidence=None,
                            relation="ocr_page_line",
                        )
                    )
            if len(candidates) >= max_candidates:
                break
    elif pages_text:
        for page_no, page_text in enumerate(pages_text, start=1):
            for idx, line_text in enumerate(_split_lines(page_text or "")):
                if len(candidates) >= max_candidates:
                    warnings.append("ocr_line_candidates_truncated")
                    break
                candidates.append(
                    _candidate(
                        candidate_id=f"ocr_p{page_no}_t{idx}",
                        value_text=line_text,
                        page=page_no,
                        bbox=None,
                        confidence=None,
                        relation="ocr_page_line",
                    )
                )
            if len(candidates) >= max_candidates:
                break
    else:
        for idx, line_text in enumerate(_split_lines(ocr_text or "")):
            if len(candidates) >= max_candidates:
                warnings.append("ocr_line_candidates_truncated")
                break
            candidates.append(
                _candidate(
                    candidate_id=f"ocr_p1_t{idx}",
                    value_text=line_text,
                    page=1,
                    bbox=None,
                    confidence=None,
                    relation="ocr_flat_line",
                )
            )

    if not candidates:
        warnings.append("ocr_line_candidates_empty")

    index = {str(item["candidate_id"]): item for item in candidates}
    llm_view = [
        {
            "candidate_id": item["candidate_id"],
            "label": item.get("label_text"),
            "value": item.get("value_text"),
            "page": item.get("page"),
            "section_id": item.get("section_id"),
            "bbox": item.get("bbox"),
            "confidence": item.get("confidence"),
            "relation": item.get("relation"),
            "conflict": False,
        }
        for item in candidates
    ]
    return {
        "schema_version": 1,
        "binder": "ocr_line_candidates_v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "candidate_index": index,
        "llm_candidates": llm_view,
        "warnings": list(dict.fromkeys(warnings)),
    }


def merge_evidence_bundles(
    primary: dict[str, Any] | None,
    fallback: dict[str, Any] | None,
    *,
    max_candidates: int = DEFAULT_MERGE_MAX_CANDIDATES,
    high_priority_ocr_reserve: int = DEFAULT_HIGH_PRIORITY_OCR_RESERVE,
) -> dict[str, Any]:
    """Merge layout (primary) + OCR (fallback) under a hard candidate budget.

    Layout remains preferred for structured associations, but a bounded reserve
    is held for high-priority unlabeled OCR lines (priority tier 0). Without
    that reserve, saturated layout bundles discard OCR header names before
    prompt compaction can prioritize them.
    """
    primary = primary if isinstance(primary, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    warnings: list[str] = list(primary.get("warnings") or []) + list(fallback.get("warnings") or [])

    primary_items = [c for c in (primary.get("candidates") or []) if isinstance(c, dict)]
    fallback_items = [c for c in (fallback.get("candidates") or []) if isinstance(c, dict)]

    reserve_cap = max(0, min(int(high_priority_ocr_reserve), max_candidates // 4))
    reserved_ocr = [
        item
        for item in fallback_items
        if evidence_candidate_priority_tier(item) == 0
    ][:reserve_cap]
    layout_budget = max_candidates - len(reserved_ocr)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _try_append(item: dict[str, Any]) -> bool:
        cid = str(item.get("candidate_id") or "").strip()
        if not cid or cid in seen:
            return True
        if len(candidates) >= max_candidates:
            return False
        seen.add(cid)
        candidates.append(item)
        return True

    layout_appended = 0
    for item in primary_items:
        if layout_appended >= layout_budget:
            break
        before = len(candidates)
        if not _try_append(item):
            break
        if len(candidates) > before:
            layout_appended += 1

    if len(primary_items) > layout_budget and reserved_ocr:
        warnings.append("merged_evidence_layout_trimmed_for_ocr_reserve")

    for item in reserved_ocr:
        if not _try_append(item):
            break

    for item in fallback_items:
        if not _try_append(item):
            break

    input_unique = _unique_count(primary_items, fallback_items)
    if len(candidates) >= max_candidates and input_unique > len(candidates):
        warnings.append("merged_evidence_candidates_truncated")

    binder = str(primary.get("binder") or "")
    if primary.get("candidate_count") and fallback.get("candidate_count"):
        binder = f"{binder}+{fallback.get('binder')}" if binder else str(fallback.get("binder"))
    elif not candidates and fallback:
        binder = str(fallback.get("binder") or "ocr_line_candidates_v1")
    elif not binder:
        binder = "evidence_binder_v1"

    index = {str(item["candidate_id"]): item for item in candidates if item.get("candidate_id")}
    llm_view = [
        {
            "candidate_id": item.get("candidate_id"),
            "label": item.get("label_text"),
            "value": item.get("value_text"),
            "page": item.get("page"),
            "section_id": item.get("section_id"),
            "row_id": item.get("row_id"),
            "column_index": item.get("column_index"),
            "bbox": item.get("bbox"),
            "confidence": item.get("confidence"),
            "relation": item.get("relation"),
            "conflict": bool(item.get("conflict")),
        }
        for item in candidates
    ]
    return {
        "schema_version": 1,
        "binder": binder,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "candidate_index": index,
        "llm_candidates": llm_view,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _unique_count(*groups: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    for group in groups:
        for item in group:
            cid = str(item.get("candidate_id") or "").strip()
            if cid:
                seen.add(cid)
    return len(seen)

def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _candidate(
    *,
    candidate_id: str,
    value_text: str,
    page: int,
    bbox: list[Any] | None,
    confidence: Any,
    relation: str,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "label_text": None,
        "value_text": value_text,
        "page": page,
        "section_id": None,
        "row_id": None,
        "column_index": None,
        "bbox": bbox,
        "confidence": confidence if confidence is not None else "unknown",
        "relation": relation,
        "association_id": None,
        "label_cell_id": None,
        "value_cell_id": None,
        "source_line_ids": [candidate_id],
        "source_word_ids": [],
        "conflict": False,
        "normalized_value": normalize_numeric_token(value_text),
    }
