"""Employee payroll-month presentation status (stable machine codes).

Maps validation outcomes and document availability to presentation buckets.
Does not evaluate payroll law — only aggregates backend validation/document signals.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from payroll_copilot.domain.enums import FindingSeverity, ValidationResult

# Presentation buckets returned to the Employee Portal.
PRESENTATION_PASSED = "passed"
PRESENTATION_ERROR = "error"
PRESENTATION_WARNING = "warning"
PRESENTATION_UNAVAILABLE = "unavailable"

LOW_CONFIDENCE_THRESHOLD = Decimal("0.70")

SEVERITY_RANK = {
    FindingSeverity.INFO.value: 1,
    FindingSeverity.WARNING.value: 2,
    FindingSeverity.CRITICAL.value: 3,
    "info": 1,
    "warning": 2,
    "critical": 3,
}


def highest_severity(codes: list[str]) -> str | None:
    if not codes:
        return None
    return max(codes, key=lambda c: SEVERITY_RANK.get(str(c).lower(), 0))


def compute_presentation_status(
    *,
    payslip_exists: bool,
    validation_exists: bool,
    overall_result: str | None,
    highest_finding_severity: str | None,
    overall_confidence: float | Decimal | None,
    validation_status: str | None = None,
) -> str:
    """Priority: error > warning > passed > unavailable.

    - Red (`error`): critical finding or overall_result critical.
    - Yellow (`warning`): warning severity, overall warnings, or low confidence.
    - Green (`passed`): validation completed with pass and no negative findings signal.
    - Gray (`unavailable`): no payslip, validation not run, incomplete, or missing data.
    """
    if not payslip_exists:
        return PRESENTATION_UNAVAILABLE
    if not validation_exists:
        return PRESENTATION_UNAVAILABLE
    if validation_status and str(validation_status).lower() in {"pending", "running", "failed"}:
        if str(validation_status).lower() == "failed":
            return PRESENTATION_ERROR
        return PRESENTATION_WARNING

    result = (overall_result or "").lower()
    severity = (highest_finding_severity or "").lower()

    if result == ValidationResult.CRITICAL.value or severity == FindingSeverity.CRITICAL.value:
        return PRESENTATION_ERROR

    conf: Decimal | None
    try:
        conf = Decimal(str(overall_confidence)) if overall_confidence is not None else None
    except Exception:
        conf = None

    if (
        result == ValidationResult.WARNINGS.value
        or severity == FindingSeverity.WARNING.value
        or (conf is not None and conf < LOW_CONFIDENCE_THRESHOLD)
    ):
        return PRESENTATION_WARNING

    if result == ValidationResult.PASS.value:
        return PRESENTATION_PASSED

    return PRESENTATION_UNAVAILABLE


def document_summary(doc: Any | None) -> dict[str, Any]:
    if doc is None:
        return {
            "exists": False,
            "document_id": None,
            "uploaded_at": None,
            "status": "missing",
            "original_filename": None,
        }
    status = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    return {
        "exists": True,
        "document_id": str(doc.id),
        "uploaded_at": doc.created_at.isoformat() if getattr(doc, "created_at", None) else None,
        "status": status,
        "original_filename": getattr(doc, "original_filename", None),
    }
