"""In-memory validation report cache for guest assistant explanations."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.assistant import ValidationReportPort

_validation_reports: dict[str, dict[str, Any]] = {}


class InMemoryValidationReportStore(ValidationReportPort):
    def get_report(
        self,
        validation_run_id: str,
        *,
        owner_guest_id: str | None = None,
    ) -> dict[str, object] | None:
        entry = _validation_reports.get(validation_run_id)
        if entry is None:
            return None
        stored_owner = str(entry.get("_owner_guest_id") or "").strip()
        # Fail closed: reports without an owner, or without a matching caller, are invisible.
        if not stored_owner or not owner_guest_id or stored_owner != owner_guest_id.strip():
            return None
        return {
            key: value
            for key, value in entry.items()
            if not str(key).startswith("_")
        }


def cache_validation_report(
    validation_run_id: str,
    report: dict[str, object],
    *,
    owner_guest_id: str,
) -> None:
    """Store a deterministic validation report scoped to a guest session."""
    owner = (owner_guest_id or "").strip()
    if not owner:
        raise ValueError("owner_guest_id is required to cache a guest validation report.")
    _validation_reports[validation_run_id] = {
        **report,
        "_owner_guest_id": owner,
    }


def clear_validation_report_cache() -> None:
    _validation_reports.clear()
