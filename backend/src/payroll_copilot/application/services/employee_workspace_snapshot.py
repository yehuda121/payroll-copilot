"""Persist and restore employee month-workspace identity/period comparison.

Snapshots live on document.metadata so month-detail can reload without
re-running OCR/extraction or validation.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipComparisonResult,
    PayslipIdentityComparisonService,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id


def comparison_snapshot(comparison: PayslipComparisonResult) -> dict[str, Any]:
    return {
        "identity_check": comparison.identity_check.to_dict(),
        "period_check": comparison.period_check.to_dict(),
        "blocks_confirmation": comparison.blocks_confirmation,
    }


def apply_comparison_snapshot(
    metadata: dict[str, Any] | None,
    comparison: PayslipComparisonResult,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    snap = comparison_snapshot(comparison)
    meta["identity_check"] = snap["identity_check"]
    meta["period_check"] = snap["period_check"]
    meta["blocks_confirmation"] = snap["blocks_confirmation"]
    return meta


def read_comparison_snapshot(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    meta = metadata or {}
    identity = meta.get("identity_check")
    period = meta.get("period_check")
    if not isinstance(identity, dict) or not isinstance(period, dict):
        return None
    return {
        "identity_check": identity,
        "period_check": period,
        "blocks_confirmation": bool(
            meta.get("blocks_confirmation")
            if "blocks_confirmation" in meta
            else identity.get("blocks_confirmation") or period.get("blocks_confirmation")
        ),
    }


def fields_for_workspace_api(raw_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize lifecycle field views to the extract-API field shape."""
    out: list[dict[str, Any]] = []
    for row in raw_fields:
        out.append(
            {
                "key": str(row.get("key") or ""),
                "value": row.get("effective_value", row.get("value")),
                "confidence": row.get("confidence"),
                "source_text": row.get("source_text"),
                "status": str(
                    row.get("extraction_status") or row.get("status") or "MISSING"
                ).upper(),
                "edited_by_user": bool(
                    row.get("edited_by_employee") or row.get("edited_by_user")
                ),
            }
        )
    return out


def rebuild_comparison(
    *,
    employee: Employee,
    national_id_encrypted: bytes | None,
    document: Document,
    extraction: DocumentExtraction,
    comparison_service: PayslipIdentityComparisonService | None = None,
) -> PayslipComparisonResult:
    """Reconstruct comparison from persisted fields + employee (no OCR)."""
    from payroll_copilot.application.use_cases.extract_guest_payslip import (
        _fields_from_structured,
    )

    service = comparison_service or PayslipIdentityComparisonService()
    meta = dict(document.metadata or {})
    selected_year = int(
        meta.get("selected_period_year")
        or (document.period.year if document.period else 0)
        or 0
    )
    selected_month = int(
        meta.get("selected_period_month")
        or (document.period.month if document.period else 0)
        or 0
    )
    settings = get_settings()
    plaintext = decrypt_national_id(
        national_id_encrypted,
        encryption_key=settings.encryption_key,
    )
    masked = (employee.metadata or {}).get("national_id_masked")
    display_name = (employee.metadata or {}).get("verified_display_name") or (
        f"{employee.first_name} {employee.last_name}"
    )
    fields, _ = _fields_from_structured(extraction.structured_data or {})
    return service.compare(
        trusted_full_name=str(display_name),
        trusted_employee_number=employee.employee_number,
        trusted_national_id_plaintext=plaintext,
        trusted_national_id_masked=masked if isinstance(masked, str) else None,
        selected_year=selected_year,
        selected_month=selected_month,
        extraction_fields=fields,
        period_resolution=str(meta.get("period_resolution") or "") or None,
    )


def patch_period_resolution_keep(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Update stored period_check after employee keeps the selected period."""
    meta = dict(metadata or {})
    meta["period_resolution"] = "keep_selected"
    period = dict(meta.get("period_check") or {})
    if period:
        period["blocks_confirmation"] = False
        period["explanation_code"] = "period_kept_selected"
        meta["period_check"] = period
    identity = meta.get("identity_check") if isinstance(meta.get("identity_check"), dict) else {}
    meta["blocks_confirmation"] = bool(identity.get("blocks_confirmation"))
    return meta
