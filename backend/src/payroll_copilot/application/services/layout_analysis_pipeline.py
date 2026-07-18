"""Phase 2 pipeline: layout_snapshot → structure → associations (parallel to LLM)."""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.ports.structure_association import (
    STRUCTURE_ANALYSIS_SCHEMA_VERSION,
    LayoutStructureConfig,
    empty_layout_analysis,
    layout_structure_config_from_settings,
)
from payroll_copilot.application.services.association_engine import associate_labels_and_values
from payroll_copilot.application.services.structure_builder import build_structure_from_layout

logger = logging.getLogger(__name__)


def build_layout_analysis(
    layout_snapshot: dict[str, Any] | None,
    *,
    config: LayoutStructureConfig | None = None,
) -> dict[str, Any]:
    """Build additive layout_analysis. Never raises into the extraction path."""
    cfg = config or LayoutStructureConfig()
    if not cfg.enabled:
        return {}

    if not layout_snapshot or not (layout_snapshot.get("pages") or []):
        return empty_layout_analysis(warning="layout_analysis_missing_layout_snapshot")

    try:
        structure = build_structure_from_layout(layout_snapshot, config=cfg)
        association = associate_labels_and_values(structure.get("pages") or [], config=cfg)
    except Exception as exc:  # noqa: BLE001
        logger.info("layout_analysis_failed error_type=%s", type(exc).__name__)
        return empty_layout_analysis(warning="layout_analysis_build_failed")

    warnings = list(structure.get("warnings") or [])
    warnings.extend(association.get("warnings") or [])

    return {
        "schema_version": STRUCTURE_ANALYSIS_SCHEMA_VERSION,
        "builder": "structure_builder_v1",
        "association_engine": "association_engine_v1",
        "pages": structure.get("pages") or [],
        "associations": association.get("associations") or [],
        "unresolved_labels": association.get("unresolved_labels") or [],
        "unresolved_values": association.get("unresolved_values") or [],
        "conflict_groups": association.get("conflict_groups") or [],
        "warnings": list(dict.fromkeys(warnings)),
    }


def create_layout_structure_config(settings: object) -> LayoutStructureConfig:
    return layout_structure_config_from_settings(settings)
