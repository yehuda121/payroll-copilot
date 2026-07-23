"""Map existing document + extraction state to analytics outcome buckets.

Reuses Document.status, lifecycle_status, and confirmation_status — no new SoT.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_REVIEW_REQUIRED,
    LIFECYCLE_ACCOUNTANT_REVIEW,
    LIFECYCLE_CONFIRMED,
    LIFECYCLE_EXTRACTION_FAILED,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_REVIEW_REQUIRED,
)
from payroll_copilot.domain.enums import DocumentStatus


class DocumentOutcome(StrEnum):
    SUCCESS = "success"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


_SUCCESS_LIFECYCLES = frozenset({LIFECYCLE_CONFIRMED, LIFECYCLE_PUBLISHED})
_REVIEW_LIFECYCLES = frozenset({LIFECYCLE_REVIEW_REQUIRED, LIFECYCLE_ACCOUNTANT_REVIEW})


def classify_document_outcome(
    document: Any,
    extraction: Any | None = None,
) -> DocumentOutcome:
    metadata = dict(getattr(document, "metadata", None) or {})
    lifecycle = str(metadata.get("lifecycle_status") or "").strip().lower()
    status = getattr(document, "status", None)
    status_value = status.value if hasattr(status, "value") else str(status or "")

    if status_value == DocumentStatus.FAILED.value or lifecycle == LIFECYCLE_EXTRACTION_FAILED:
        return DocumentOutcome.FAILED

    confirmation = None
    if extraction is not None:
        confirmation = str(getattr(extraction, "confirmation_status", None) or "").strip().lower()

    if confirmation == CONFIRMATION_CONFIRMED or lifecycle in _SUCCESS_LIFECYCLES:
        return DocumentOutcome.SUCCESS

    if (
        confirmation == CONFIRMATION_REVIEW_REQUIRED
        or lifecycle in _REVIEW_LIFECYCLES
        or status_value == DocumentStatus.PROCESSED.value
    ):
        return DocumentOutcome.REVIEW_REQUIRED

    # uploaded / processing / incomplete — treat as still requiring review for dashboards
    return DocumentOutcome.REVIEW_REQUIRED
