"""In-memory validation report cache for guest assistant explanations."""

from __future__ import annotations

from payroll_copilot.application.ports.assistant import ValidationReportPort

_validation_reports: dict[str, dict[str, object]] = {}


class InMemoryValidationReportStore(ValidationReportPort):
    def get_report(self, validation_run_id: str) -> dict[str, object] | None:
        return _validation_reports.get(validation_run_id)


def cache_validation_report(validation_run_id: str, report: dict[str, object]) -> None:
    """Store a deterministic validation report for later assistant retrieval."""
    _validation_reports[validation_run_id] = report


def clear_validation_report_cache() -> None:
    _validation_reports.clear()
