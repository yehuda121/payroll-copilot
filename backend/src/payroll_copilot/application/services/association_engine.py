"""Deterministic Association Engine (Phase 2).

Associates label-shaped cells with value-shaped cells using geometry only:
page, block/row/column membership, coordinates, reading order, distance, alignment.

No LLM. No payroll field lexicon. Conflicts are recorded, never silently guessed.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.structure_association import (
    ConfidenceBand,
    LayoutStructureConfig,
)
from payroll_copilot.application.services.parser_geometry import (
    horizontal_distance,
    normalized_distance,
    vertical_overlap_ratio,
)


def associate_labels_and_values(
    structure_pages: list[dict[str, Any]],
    *,
    config: LayoutStructureConfig | None = None,
) -> dict[str, Any]:
    """Return associations, unresolved tokens, and conflict groups."""
    cfg = config or LayoutStructureConfig()
    associations: list[dict[str, Any]] = []
    unresolved_labels: list[str] = []
    unresolved_values: list[str] = []
    warnings: list[str] = []

    for page in structure_pages:
        page_result = _associate_page(page, cfg=cfg)
        associations.extend(page_result["associations"])
        unresolved_labels.extend(page_result["unresolved_labels"])
        unresolved_values.extend(page_result["unresolved_values"])
        warnings.extend(page_result["warnings"])

    conflict_groups = _build_conflict_groups(associations)
    # Mark associations that participate in conflicts.
    conflicted_ids = {aid for group in conflict_groups for aid in group.get("association_ids") or []}
    for item in associations:
        if item["id"] in conflicted_ids:
            item["conflict"] = True
            # Conflict strategy: demote confidence one band; keep alternatives visible.
            item["confidence"] = _demote(item.get("confidence") or "unknown")

    return {
        "associations": associations,
        "unresolved_labels": unresolved_labels,
        "unresolved_values": unresolved_values,
        "conflict_groups": conflict_groups,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _associate_page(page: dict[str, Any], *, cfg: LayoutStructureConfig) -> dict[str, Any]:
    cells = [cell for cell in (page.get("cells") or []) if isinstance(cell, dict)]
    rows = {row["id"]: row for row in (page.get("rows") or []) if isinstance(row, dict)}
    page_width = float(page.get("width") or 1.0) or 1.0
    page_height = float(page.get("height") or 1.0) or 1.0
    page_number = int(page.get("page") or 1)

    labels = [cell for cell in cells if cell.get("token_kind") in {"label", "mixed"}]
    values = [cell for cell in cells if cell.get("token_kind") in {"value", "mixed"}]

    associations: list[dict[str, Any]] = []
    assoc_index = 0

    for label in labels:
        candidates = _candidates_for_label(
            label,
            values=values,
            rows=rows,
            page_width=page_width,
            page_height=page_height,
            cfg=cfg,
        )
        if not candidates:
            continue

        candidates.sort(key=lambda item: (-item["score"], item["value_id"]))
        top = candidates[: max(1, cfg.max_alternatives)]
        best = top[0]
        assoc_id = f"p{page_number}_a{assoc_index}"
        assoc_index += 1
        associations.append(
            {
                "id": assoc_id,
                "page": page_number,
                "label_id": label["id"],
                "label_text": label.get("text"),
                "value_id": best["value_id"],
                "value_text": best["value_text"],
                "relation": best["relation"],
                "confidence": best["confidence"],
                "score": round(best["score"], 4),
                "evidence": best["evidence"],
                "alternatives": [
                    {
                        "value_id": alt["value_id"],
                        "value_text": alt["value_text"],
                        "relation": alt["relation"],
                        "confidence": alt["confidence"],
                        "score": round(alt["score"], 4),
                    }
                    for alt in top[1:]
                ],
                "conflict": False,
                "conflict_group": None,
            }
        )

    associated_labels = {item["label_id"] for item in associations}
    associated_values = {item["value_id"] for item in associations}
    unresolved_labels = [cell["id"] for cell in labels if cell["id"] not in associated_labels]
    # Values that are only alternatives still count as "touched"; truly free values remain unresolved.
    alt_values = {
        alt["value_id"]
        for item in associations
        for alt in item.get("alternatives") or []
    }
    unresolved_values = [
        cell["id"]
        for cell in values
        if cell["id"] not in associated_values and cell["id"] not in alt_values
    ]

    warnings: list[str] = []
    if not labels:
        warnings.append("association_engine_no_label_cells")
    if not values:
        warnings.append("association_engine_no_value_cells")

    return {
        "associations": associations,
        "unresolved_labels": unresolved_labels,
        "unresolved_values": unresolved_values,
        "warnings": warnings,
    }


def _candidates_for_label(
    label: dict[str, Any],
    *,
    values: list[dict[str, Any]],
    rows: dict[str, dict[str, Any]],
    page_width: float,
    page_height: float,
    cfg: LayoutStructureConfig,
) -> list[dict[str, Any]]:
    """Score value candidates for one label.

    Matching strategy (deterministic, ordered by score):
    1. same_row — shared row_id, strong vertical overlap, horizontal neighbor
    2. same_column_below — same column_index, value below label within gap budget
    3. nearest_neighbor — normalized distance within budgets; blocked if different tables
       when both cells belong to distinct tables

    Tie-breaking: higher score wins; equal score → stable value_id order (caller sorts).
    """
    label_bbox = label.get("bbox")
    if not _bbox_ok(label_bbox):
        return []

    label_row = rows.get(str(label.get("row_id") or ""))
    out: list[dict[str, Any]] = []

    for value in values:
        if value.get("id") == label.get("id"):
            continue
        value_bbox = value.get("bbox")
        if not _bbox_ok(value_bbox):
            continue

        # Conflict strategy — mixed tokens: a cell may be both label and value.
        # Allow self-skip only; mixed↔mixed associations remain valid candidates.

        relation = None
        evidence: dict[str, Any] = {
            "page": label.get("row_id", ""),
            "label_row_id": label.get("row_id"),
            "value_row_id": value.get("row_id"),
            "label_column_index": label.get("column_index"),
            "value_column_index": value.get("column_index"),
            "label_bbox": list(label_bbox),
            "value_bbox": list(value_bbox),
        }

        same_row = label.get("row_id") and label.get("row_id") == value.get("row_id")
        overlap = vertical_overlap_ratio(label_bbox, value_bbox)
        h_gap = horizontal_distance(label_bbox, value_bbox)
        h_gap_ratio = h_gap / page_width

        score = 0.0
        confidence: ConfidenceBand = "unknown"

        if same_row and overlap >= 0.4 and h_gap_ratio <= cfg.max_same_row_gap_ratio:
            # Prefer the nearer horizontal side; do not assume LTR vs RTL.
            relation = "same_row"
            proximity = 1.0 - min(h_gap_ratio / max(cfg.max_same_row_gap_ratio, 1e-6), 1.0)
            score = 0.55 + 0.35 * proximity + 0.10 * min(overlap, 1.0)
            confidence = _band_from_score(score)
            evidence["horizontal_gap"] = h_gap
            evidence["vertical_overlap"] = overlap
        else:
            # Column-below association (header → body cell).
            same_col = (
                label.get("column_index") is not None
                and value.get("column_index") is not None
                and label.get("column_index") == value.get("column_index")
            )
            label_bottom = float(label_bbox[1]) + float(label_bbox[3])
            value_top = float(value_bbox[1])
            below_gap = value_top - label_bottom
            below_ratio = below_gap / page_height
            if (
                same_col
                and below_gap >= -0.5 * float(label_bbox[3])
                and below_ratio <= cfg.max_below_gap_ratio
            ):
                relation = "same_column_below"
                proximity = 1.0 - min(max(below_ratio, 0.0) / max(cfg.max_below_gap_ratio, 1e-6), 1.0)
                score = 0.45 + 0.40 * proximity
                confidence = _band_from_score(score)
                evidence["below_gap"] = below_gap
            else:
                # Nearest-neighbor fallback with table barrier.
                label_table = label_row.get("table_id") if label_row else None
                value_row = rows.get(str(value.get("row_id") or ""))
                value_table = value_row.get("table_id") if value_row else None
                if label_table and value_table and label_table != value_table:
                    continue
                dist = normalized_distance(
                    label_bbox,
                    value_bbox,
                    page_width=page_width,
                    page_height=page_height,
                )
                if dist > max(cfg.max_same_row_gap_ratio, cfg.max_below_gap_ratio):
                    continue
                relation = "nearest_neighbor"
                score = max(0.15, 0.40 - dist)
                confidence = _band_from_score(score)
                evidence["normalized_distance"] = dist

        if relation is None:
            continue

        out.append(
            {
                "value_id": value["id"],
                "value_text": value.get("text"),
                "relation": relation,
                "score": score,
                "confidence": confidence,
                "evidence": evidence,
            }
        )

    return out


def _build_conflict_groups(associations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conflict strategy documentation:

    1. Multiple labels → one value: all best associations sharing value_id form a group.
    2. One label → multiple near-equal alternatives: already stored on alternatives[];
       only promote to conflict_group when two *best* associations collide on a value.
    3. Ambiguous rows / missing layout: produce unresolved_* lists instead of guesses.
    Never deletes losing candidates; demotes confidence and sets conflict=true.
    """
    by_value: dict[str, list[str]] = {}
    for item in associations:
        by_value.setdefault(str(item["value_id"]), []).append(str(item["id"]))

    groups: list[dict[str, Any]] = []
    group_no = 0
    for value_id, assoc_ids in by_value.items():
        if len(assoc_ids) < 2:
            continue
        group_id = f"conflict_{group_no}"
        group_no += 1
        groups.append(
            {
                "id": group_id,
                "type": "multiple_labels_one_value",
                "value_id": value_id,
                "association_ids": assoc_ids,
            }
        )
        for item in associations:
            if item["id"] in assoc_ids:
                item["conflict_group"] = group_id
    return groups


def _band_from_score(score: float) -> ConfidenceBand:
    """Map deterministic geometric score to discrete bands (not invented probabilities)."""
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    if score >= 0.30:
        return "low"
    return "unknown"


def _demote(band: str) -> ConfidenceBand:
    order: list[ConfidenceBand] = ["high", "medium", "low", "unknown"]
    if band not in order:
        return "unknown"
    index = order.index(band)  # type: ignore[arg-type]
    return order[min(index + 1, len(order) - 1)]


def _bbox_ok(bbox: Any) -> bool:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    try:
        _x, _y, w, h = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return False
    return w > 0 and h > 0
