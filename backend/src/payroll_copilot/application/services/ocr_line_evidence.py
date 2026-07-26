"""OCR-line evidence candidates when layout analysis is unavailable.

Compact addressable values so semantic_v1 can still ground unlabeled header text.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.parser_evidence import normalize_numeric_token


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
    max_candidates: int = 400,
) -> dict[str, Any]:
    """Prefer layout binder candidates; append OCR-line candidates with unique IDs."""
    primary = primary if isinstance(primary, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = list(primary.get("warnings") or []) + list(fallback.get("warnings") or [])
    seen: set[str] = set()

    for source in (primary.get("candidates") or [], fallback.get("candidates") or []):
        for item in source:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("candidate_id") or "").strip()
            if not cid or cid in seen:
                continue
            if len(candidates) >= max_candidates:
                warnings.append("merged_evidence_candidates_truncated")
                break
            seen.add(cid)
            candidates.append(item)
        if len(candidates) >= max_candidates:
            break

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
