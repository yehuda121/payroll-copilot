"""Phase 2 structure / association ports (deterministic, payroll-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

STRUCTURE_ANALYSIS_SCHEMA_VERSION = 1

ConfidenceBand = Literal["high", "medium", "low", "unknown"]
TokenKind = Literal["label", "value", "mixed", "unknown"]


@dataclass(frozen=True, slots=True)
class LayoutStructureConfig:
    """Feature flag + tunables for Structure Builder / Association Engine."""

    enabled: bool = False
    # Row clustering: min vertical overlap ratio to merge lines into one row.
    row_overlap_min: float = 0.45
    # Split a line into multiple cells when intra-line gap exceeds this × median word width.
    cell_gap_factor: float = 1.0
    # 1D column clustering threshold as fraction of median cell width.
    column_cluster_factor: float = 0.65
    # Minimum consecutive multi-cell rows required before emitting a table.
    min_table_rows: int = 3
    # Vertical gap (× median row height) that starts a new section.
    section_gap_factor: float = 2.5
    # Association distance budgets (normalized to page width/height).
    max_same_row_gap_ratio: float = 0.45
    max_below_gap_ratio: float = 0.12
    max_alternatives: int = 3


def layout_structure_config_from_settings(settings: object) -> LayoutStructureConfig:
    return LayoutStructureConfig(
        enabled=bool(getattr(settings, "layout_structure_enabled", False)),
        row_overlap_min=float(getattr(settings, "layout_structure_row_overlap_min", 0.45)),
        cell_gap_factor=float(getattr(settings, "layout_structure_cell_gap_factor", 1.0)),
        column_cluster_factor=float(getattr(settings, "layout_structure_column_cluster_factor", 0.65)),
        min_table_rows=int(getattr(settings, "layout_structure_min_table_rows", 3)),
        section_gap_factor=float(getattr(settings, "layout_structure_section_gap_factor", 2.5)),
        max_same_row_gap_ratio=float(
            getattr(settings, "layout_structure_max_same_row_gap_ratio", 0.45)
        ),
        max_below_gap_ratio=float(getattr(settings, "layout_structure_max_below_gap_ratio", 0.12)),
        max_alternatives=int(getattr(settings, "layout_structure_max_alternatives", 3)),
    )


def empty_layout_analysis(*, warning: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": STRUCTURE_ANALYSIS_SCHEMA_VERSION,
        "builder": "structure_builder_v1",
        "association_engine": "association_engine_v1",
        "pages": [],
        "associations": [],
        "unresolved_labels": [],
        "unresolved_values": [],
        "conflict_groups": [],
        "warnings": [],
    }
    if warning:
        payload["warnings"] = [warning]
    return payload
