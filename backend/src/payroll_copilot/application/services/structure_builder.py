"""Deterministic Structure Builder (Phase 2).

Transforms layout_snapshot pages into sections / rows / columns / optional tables.
No payroll semantics. No LLM. Never fabricates geometry that is not supported by
bounding boxes and reading order in the snapshot.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from payroll_copilot.application.ports.structure_association import (
    ConfidenceBand,
    LayoutStructureConfig,
    TokenKind,
)
from payroll_copilot.application.services.parser_geometry import vertical_overlap_ratio

_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_DIGIT_RE = re.compile(r"\d")
# Shape-only value patterns (not payroll field names).
_VALUE_RE = re.compile(
    r"""
    ^[\s\$€£₪]*
    (
        \d{1,3}([, ]\d{3})*([.]\d+)?
      | \d+[.,]\d+
      | \d+
      | \d{1,2}[/.\-]\d{1,4}(?:[/.\-]\d{2,4})?
    )
    [\s%]*$
    """,
    re.VERBOSE,
)


def classify_token_kind(text: str) -> TokenKind:
    """Classify a token by character shape only (no payroll lexicon)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "unknown"
    has_letter = bool(_LETTER_RE.search(cleaned))
    has_digit = bool(_DIGIT_RE.search(cleaned))
    compact = cleaned.replace(" ", "")
    looks_value = bool(_VALUE_RE.match(compact)) or (
        has_digit and not has_letter and len(_DIGIT_RE.findall(cleaned)) >= 1
    )
    if looks_value and not has_letter:
        return "value"
    if looks_value and has_letter:
        return "mixed"
    if has_letter and not has_digit:
        return "label"
    if has_letter and has_digit:
        return "mixed"
    return "unknown"


def build_structure_from_layout(
    layout_snapshot: dict[str, Any],
    *,
    config: LayoutStructureConfig | None = None,
) -> dict[str, Any]:
    """Build per-page structure graph from a Phase 1 layout_snapshot."""
    cfg = config or LayoutStructureConfig()
    warnings: list[str] = list(layout_snapshot.get("warnings") or [])
    pages_out: list[dict[str, Any]] = []

    for page in layout_snapshot.get("pages") or []:
        if not isinstance(page, dict):
            continue
        pages_out.append(_build_page(page, cfg=cfg, warnings=warnings))

    if not pages_out:
        warnings.append("structure_builder_empty_layout")

    return {
        "pages": pages_out,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _build_page(
    page: dict[str, Any],
    *,
    cfg: LayoutStructureConfig,
    warnings: list[str],
) -> dict[str, Any]:
    page_number = int(page.get("page") or 1)
    width = float(page.get("width") or 0.0) or None
    height = float(page.get("height") or 0.0) or None

    lines = [line for line in (page.get("lines") or []) if isinstance(line, dict)]
    words = [word for word in (page.get("words") or []) if isinstance(word, dict)]
    words_by_line: dict[str, list[dict[str, Any]]] = {}
    for word in words:
        line_id = str(word.get("line_id") or "")
        if line_id:
            words_by_line.setdefault(line_id, []).append(word)

    usable_lines = [line for line in lines if _bbox_ok(line.get("bbox"))]
    if not usable_lines:
        # Preserve block hierarchy without inventing rows/tables.
        warnings.append(f"structure_builder_no_geometry_page_{page_number}")
        return {
            "page": page_number,
            "width": width,
            "height": height,
            "sections": [],
            "tables": [],
            "rows": [],
            "cells": [],
            "blocks_preserved": list(page.get("blocks") or []),
            "confidence": "unknown",
        }

    row_groups = _cluster_rows(usable_lines, overlap_min=cfg.row_overlap_min)
    cells: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for row_index, group in enumerate(row_groups):
        row_id = f"p{page_number}_r{row_index}"
        row_cells = _cells_for_row(
            page_number=page_number,
            row_id=row_id,
            lines=group,
            words_by_line=words_by_line,
            gap_factor=cfg.cell_gap_factor,
        )
        cell_ids = [cell["id"] for cell in row_cells]
        cells.extend(row_cells)
        rows.append(
            {
                "id": row_id,
                "bbox": _union_bboxes([cell["bbox"] for cell in row_cells if cell.get("bbox")]),
                "confidence": _row_confidence(row_cells),
                "section_id": None,
                "table_id": None,
                "reading_index": row_index,
                "cell_ids": cell_ids,
            }
        )

    # Estimate page size from content when snapshot omitted dimensions.
    if width is None or height is None:
        all_boxes = [cell["bbox"] for cell in cells if cell.get("bbox")]
        if all_boxes:
            width = width or max(box[0] + box[2] for box in all_boxes)
            height = height or max(box[1] + box[3] for box in all_boxes)

    columns = _detect_columns(cells, rows, cluster_factor=cfg.column_cluster_factor)
    _assign_column_indices(cells, columns)

    tables, table_confidence_notes = _detect_tables(
        page_number=page_number,
        rows=rows,
        cells=cells,
        columns=columns,
        min_table_rows=cfg.min_table_rows,
    )
    warnings.extend(table_confidence_notes)

    sections = _detect_sections(
        page_number=page_number,
        rows=rows,
        gap_factor=cfg.section_gap_factor,
    )

    return {
        "page": page_number,
        "width": width,
        "height": height,
        "sections": sections,
        "tables": tables,
        "rows": rows,
        "cells": cells,
        "columns": columns,
        "blocks_preserved": list(page.get("blocks") or []),
        "confidence": _page_confidence(rows, tables),
    }


def _cluster_rows(
    lines: list[dict[str, Any]],
    *,
    overlap_min: float,
) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        lines,
        key=lambda line: (
            float(line["bbox"][1]),
            float(line.get("reading_index") if line.get("reading_index") is not None else line["bbox"][0]),
        ),
    )
    groups: list[list[dict[str, Any]]] = []
    for line in ordered:
        bbox = line["bbox"]
        placed = False
        for group in groups:
            # Compare against the running union of the row.
            union = _union_bboxes([item["bbox"] for item in group])
            if union and vertical_overlap_ratio(bbox, union) >= overlap_min:
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])
    return groups


def _cells_for_row(
    *,
    page_number: int,
    row_id: str,
    lines: list[dict[str, Any]],
    words_by_line: dict[str, list[dict[str, Any]]],
    gap_factor: float,
) -> list[dict[str, Any]]:
    """Build left-to-right cells for a row.

    Prefer word-gap splits when words exist; otherwise one cell per line.
    """
    fragments: list[dict[str, Any]] = []
    for line in lines:
        line_id = str(line.get("id") or "")
        words = [
            word
            for word in words_by_line.get(line_id, [])
            if _bbox_ok(word.get("bbox")) and str(word.get("text") or "").strip()
        ]
        if len(words) >= 2:
            fragments.extend(_split_words_by_gap(words, gap_factor=gap_factor))
        else:
            text = str(line.get("text") or "").strip()
            if not text and words:
                text = " ".join(str(w.get("text") or "") for w in words).strip()
            if not text:
                continue
            fragments.append(
                {
                    "text": text,
                    "bbox": list(line["bbox"]),
                    "source_line_ids": [line_id] if line_id else [],
                    "source_word_ids": [str(w.get("id")) for w in words if w.get("id")],
                    "confidence": line.get("confidence"),
                }
            )

    fragments.sort(key=lambda item: float(item["bbox"][0]))
    cells: list[dict[str, Any]] = []
    for index, frag in enumerate(fragments):
        cell_id = f"{row_id}_c{index}"
        cells.append(
            {
                "id": cell_id,
                "text": frag["text"],
                "bbox": frag["bbox"],
                "row_id": row_id,
                "column_index": None,
                "token_kind": classify_token_kind(frag["text"]),
                "source_line_ids": frag["source_line_ids"],
                "source_word_ids": frag["source_word_ids"],
                "confidence": _cell_confidence(frag.get("confidence")),
            }
        )
    return cells


def _split_words_by_gap(
    words: list[dict[str, Any]],
    *,
    gap_factor: float,
) -> list[dict[str, Any]]:
    ordered = sorted(words, key=lambda word: float(word["bbox"][0]))
    widths = [float(word["bbox"][2]) for word in ordered if float(word["bbox"][2]) > 0]
    median_w = statistics.median(widths) if widths else 10.0
    # Split on gaps at least as wide as a typical word (or gap_factor × median).
    threshold = max(median_w * gap_factor, 1.0)

    groups: list[list[dict[str, Any]]] = [[ordered[0]]]
    for word in ordered[1:]:
        prev = groups[-1][-1]
        prev_right = float(prev["bbox"][0]) + float(prev["bbox"][2])
        gap = float(word["bbox"][0]) - prev_right
        if gap >= threshold:
            groups.append([word])
        else:
            groups[-1].append(word)

    fragments: list[dict[str, Any]] = []
    for group in groups:
        text = " ".join(str(item.get("text") or "").strip() for item in group).strip()
        if not text:
            continue
        fragments.append(
            {
                "text": text,
                "bbox": _union_bboxes([item["bbox"] for item in group]),
                "source_line_ids": list(
                    dict.fromkeys(str(item.get("line_id")) for item in group if item.get("line_id"))
                ),
                "source_word_ids": [str(item.get("id")) for item in group if item.get("id")],
                "confidence": None,
            }
        )
    return fragments


def _detect_columns(
    cells: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    cluster_factor: float,
) -> list[dict[str, Any]]:
    multi_cell_rows = [row for row in rows if len(row.get("cell_ids") or []) >= 2]
    if len(multi_cell_rows) < 2:
        return []

    centers: list[float] = []
    widths: list[float] = []
    multi_row_ids = {row["id"] for row in multi_cell_rows}
    for cell in cells:
        if cell.get("row_id") not in multi_row_ids:
            continue
        bbox = cell.get("bbox")
        if not _bbox_ok(bbox):
            continue
        centers.append(float(bbox[0]) + float(bbox[2]) / 2.0)
        widths.append(float(bbox[2]))

    if len(centers) < 2:
        return []

    median_w = statistics.median(widths) if widths else 20.0
    threshold = max(median_w * cluster_factor, 1.0)
    clusters = _cluster_1d(centers, threshold=threshold)
    columns: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters):
        x_center = statistics.mean(cluster)
        columns.append(
            {
                "id": f"col_{index}",
                "index": index,
                "x_center": x_center,
                "confidence": "medium" if len(cluster) >= 3 else "low",
            }
        )
    return columns


def _assign_column_indices(cells: list[dict[str, Any]], columns: list[dict[str, Any]]) -> None:
    if not columns:
        return
    for cell in cells:
        bbox = cell.get("bbox")
        if not _bbox_ok(bbox):
            continue
        cx = float(bbox[0]) + float(bbox[2]) / 2.0
        best = min(columns, key=lambda col: abs(float(col["x_center"]) - cx))
        cell["column_index"] = int(best["index"])


def _detect_tables(
    *,
    page_number: int,
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    min_table_rows: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Emit tables only when consecutive multi-cell rows share column structure.

    Conflict strategy — broken / weak grids:
    - Fewer than min_table_rows consecutive multi-cell rows → no table (keep rows).
    - Column count variance too high → no table; warning recorded.
    Never invents a table from sparse single-cell rows.
    """
    notes: list[str] = []
    if len(columns) < 2:
        notes.append("structure_builder_table_skipped_insufficient_columns")
        return [], notes

    cells_by_id = {cell["id"]: cell for cell in cells}
    flags = []
    for row in rows:
        cell_ids = row.get("cell_ids") or []
        multi = len(cell_ids) >= 2
        col_idxs = [
            cells_by_id[cid].get("column_index")
            for cid in cell_ids
            if cid in cells_by_id and cells_by_id[cid].get("column_index") is not None
        ]
        flags.append((multi, len(set(col_idxs)), row["id"]))

    tables: list[dict[str, Any]] = []
    index = 0
    table_no = 0
    while index < len(flags):
        multi, col_count, _row_id = flags[index]
        if not multi or col_count < 2:
            index += 1
            continue
        start = index
        counts = [col_count]
        index += 1
        while index < len(flags) and flags[index][0] and flags[index][1] >= 2:
            counts.append(flags[index][1])
            index += 1
        run_len = index - start
        if run_len < min_table_rows:
            notes.append("structure_builder_table_skipped_short_run")
            continue
        # Reject runs with unstable column cardinality.
        if max(counts) - min(counts) > 1:
            notes.append("structure_builder_table_skipped_unstable_columns")
            continue

        row_slice = rows[start:index]
        row_ids = [row["id"] for row in row_slice]
        table_id = f"p{page_number}_t{table_no}"
        table_no += 1
        confidence: ConfidenceBand
        if run_len >= 5 and max(counts) - min(counts) == 0:
            confidence = "high"
        elif run_len >= min_table_rows:
            confidence = "medium"
        else:
            confidence = "low"

        if confidence == "low":
            # Keep original row structure; do not emit a weak table object.
            notes.append("structure_builder_table_suppressed_low_confidence")
            continue

        bbox = _union_bboxes([row["bbox"] for row in row_slice if row.get("bbox")])
        for row in row_slice:
            row["table_id"] = table_id
        tables.append(
            {
                "id": table_id,
                "bbox": bbox,
                "confidence": confidence,
                "column_count": int(max(set(counts), key=counts.count)) if counts else len(columns),
                "row_ids": row_ids,
                "column_ids": [col["id"] for col in columns],
            }
        )

    return tables, list(dict.fromkeys(notes))


def _detect_sections(
    *,
    page_number: int,
    rows: list[dict[str, Any]],
    gap_factor: float,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    heights = [
        float(row["bbox"][3])
        for row in rows
        if _bbox_ok(row.get("bbox")) and float(row["bbox"][3]) > 0
    ]
    median_h = statistics.median(heights) if heights else 12.0
    gap_threshold = median_h * gap_factor

    sections: list[dict[str, Any]] = []
    current_ids: list[str] = []
    current_boxes: list[list[float]] = []
    prev_bottom: float | None = None

    for row in rows:
        bbox = row.get("bbox")
        if not _bbox_ok(bbox):
            current_ids.append(row["id"])
            continue
        top = float(bbox[1])
        bottom = float(bbox[1]) + float(bbox[3])
        if prev_bottom is not None and (top - prev_bottom) > gap_threshold and current_ids:
            sections.append(_section_dict(page_number, len(sections), current_ids, current_boxes))
            current_ids = []
            current_boxes = []
        current_ids.append(row["id"])
        current_boxes.append(list(bbox))
        prev_bottom = bottom

    if current_ids:
        sections.append(_section_dict(page_number, len(sections), current_ids, current_boxes))

    for section in sections:
        for row in rows:
            if row["id"] in section["row_ids"]:
                row["section_id"] = section["id"]
                table_id = row.get("table_id")
                if table_id and table_id not in section["table_ids"]:
                    section["table_ids"].append(table_id)
    return sections


def _section_dict(
    page_number: int,
    index: int,
    row_ids: list[str],
    boxes: list[list[float]],
) -> dict[str, Any]:
    return {
        "id": f"p{page_number}_s{index}",
        "bbox": _union_bboxes(boxes),
        "confidence": "medium" if len(row_ids) >= 2 else "low",
        "row_ids": list(row_ids),
        "table_ids": [],
    }


def _cluster_1d(values: list[float], *, threshold: float) -> list[list[float]]:
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if abs(value - statistics.mean(clusters[-1])) <= threshold:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return clusters


def _union_bboxes(boxes: list[Any]) -> list[float] | None:
    valid = [box for box in boxes if _bbox_ok(box)]
    if not valid:
        return None
    x0 = min(float(box[0]) for box in valid)
    y0 = min(float(box[1]) for box in valid)
    x1 = max(float(box[0]) + float(box[2]) for box in valid)
    y1 = max(float(box[1]) + float(box[3]) for box in valid)
    return [x0, y0, x1 - x0, y1 - y0]


def _bbox_ok(bbox: Any) -> bool:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    try:
        _x, _y, w, h = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return False
    return w > 0 and h > 0


def _row_confidence(cells: list[dict[str, Any]]) -> ConfidenceBand:
    if not cells:
        return "unknown"
    if all(_bbox_ok(cell.get("bbox")) for cell in cells):
        return "high" if len(cells) >= 1 else "unknown"
    return "low"


def _cell_confidence(raw: Any) -> ConfidenceBand:
    if raw is None:
        return "medium"
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 0.85:
        return "high"
    if value >= 0.6:
        return "medium"
    if value > 0:
        return "low"
    return "unknown"


def _page_confidence(rows: list[dict[str, Any]], tables: list[dict[str, Any]]) -> ConfidenceBand:
    if not rows:
        return "unknown"
    if tables and any(table.get("confidence") == "high" for table in tables):
        return "high"
    if rows:
        return "medium"
    return "low"
