"""Shared Document freeze → Canonical Projector (Phase 4).

Guest confirm, employee confirm, and batch draft-freeze all use this helper so
L2 authority is produced the same way; only persistence adapters differ.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.document_projector import (
    project_document_to_structured,
)


def freeze_and_project(
    document_model: dict[str, Any] | None,
    *,
    parser_method: str = "document_freeze_projector_v1",
    candidate_index: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Project a frozen DocumentInstance into authoritative structured_data.

    Does not mutate the Document. Callers persist confirmation/freeze metadata
    beside the returned snapshot.
    """
    projected, warnings = project_document_to_structured(
        document_model,
        parser_method=parser_method,
        candidate_index=candidate_index,
    )
    return projected.model_dump(mode="json"), list(warnings)
