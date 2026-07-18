"""Hybrid Layout Provider — Phase 1 layout preservation.

Prefer native PDF geometry when available; otherwise project OCRResult boxes.
Never invents tokens. Contains no payroll semantics.
"""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.ports.layout import (
    LayoutBuildRequest,
    LayoutSnapshotConfig,
    layout_snapshot_config_from_settings,
)
from payroll_copilot.infrastructure.layout.ocr_layout_snapshot import layout_snapshot_from_ocr
from payroll_copilot.infrastructure.layout.pdf_native_layout import extract_native_pdf_layout

logger = logging.getLogger(__name__)


def _has_usable_geometry(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    for page in snapshot.get("pages") or []:
        for line in page.get("lines") or []:
            bbox = line.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0:
                return True
        for word in page.get("words") or []:
            bbox = word.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0:
                return True
        if page.get("lines") or page.get("words"):
            # Tokens without boxes still count as partial structure.
            return True
    return False


class HybridLayoutProvider:
    """Build additive layout_snapshot dicts for persistence."""

    def __init__(self, config: LayoutSnapshotConfig | None = None) -> None:
        self._config = config or LayoutSnapshotConfig()

    def build(self, request: LayoutBuildRequest) -> dict[str, Any]:
        if not self._config.enabled:
            return {}

        warnings: list[str] = []
        media_type = (request.media_type or "").split(";")[0].strip().lower()
        is_pdf = media_type == "application/pdf" or (
            request.filename or ""
        ).lower().endswith(".pdf")

        native: dict[str, Any] | None = None
        if is_pdf and request.content:
            try:
                native = extract_native_pdf_layout(
                    request.content,
                    include_words=self._config.include_words,
                    max_pages=self._config.max_pages,
                    max_words=self._config.max_words,
                    max_lines=self._config.max_lines,
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("layout_snapshot native_pdf_failed error_type=%s", type(exc).__name__)
                warnings.append("layout_snapshot_native_pdf_failed")
                native = None

        if _has_usable_geometry(native):
            assert native is not None
            merged_warnings = list(native.get("warnings") or [])
            merged_warnings.extend(warnings)
            native["warnings"] = list(dict.fromkeys(merged_warnings))
            return native

        if native is not None:
            warnings.append("layout_snapshot_native_pdf_unusable")

        try:
            snapshot = layout_snapshot_from_ocr(
                request.ocr_result,
                include_words=self._config.include_words,
                max_pages=self._config.max_pages,
                max_words=self._config.max_words,
                max_lines=self._config.max_lines,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("layout_snapshot ocr_projection_failed error_type=%s", type(exc).__name__)
            return {
                "schema_version": 1,
                "provider": "hybrid_layout_v1",
                "source": "unavailable",
                "coordinate_format": "xywh",
                "coordinate_space": "unknown",
                "engine": request.ocr_result.engine if request.ocr_result else None,
                "page_count": 0,
                "truncated": False,
                "pages": [],
                "warnings": warnings + ["layout_snapshot_ocr_projection_failed"],
            }

        merged = list(snapshot.get("warnings") or [])
        merged.extend(warnings)
        snapshot["warnings"] = list(dict.fromkeys(merged))
        return snapshot


def create_layout_provider(settings: object) -> HybridLayoutProvider:
    return HybridLayoutProvider(layout_snapshot_config_from_settings(settings))
