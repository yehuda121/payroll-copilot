"""Layout preservation port (Phase 1).

Preserves document geometry and reading structure only.
Must not contain payroll field mapping, association, or validation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from payroll_copilot.application.ports.ocr import OCRResult

LAYOUT_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class LayoutSnapshotConfig:
    """Feature-flagged controls for layout snapshot generation."""

    enabled: bool = False
    include_words: bool = True
    max_pages: int = 20
    max_words: int = 8_000
    max_lines: int = 2_000


def layout_snapshot_config_from_settings(settings: object) -> LayoutSnapshotConfig:
    return LayoutSnapshotConfig(
        enabled=bool(getattr(settings, "layout_snapshot_enabled", False)),
        include_words=bool(getattr(settings, "layout_snapshot_include_words", True)),
        max_pages=int(getattr(settings, "layout_snapshot_max_pages", 20)),
        max_words=int(getattr(settings, "layout_snapshot_max_words", 8_000)),
        max_lines=int(getattr(settings, "layout_snapshot_max_lines", 2_000)),
    )


@dataclass(frozen=True, slots=True)
class LayoutBuildRequest:
    """Inputs available when building a layout snapshot after OCR."""

    content: bytes
    media_type: str
    ocr_result: OCRResult
    filename: str | None = None


@runtime_checkable
class LayoutProvider(Protocol):
    """Build an additive layout snapshot without changing extraction semantics."""

    def build(self, request: LayoutBuildRequest) -> dict[str, Any]:
        """Return a JSON-serializable layout_snapshot dict.

        Never invents tokens or geometry. May return a partial snapshot with
        warnings when only some structure is available.
        """
        ...
