"""Ports for the payroll investigation agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from payroll_copilot.domain.investigation.types import (
    InvestigationResult,
    PeriodRef,
    PeriodSnapshot,
)


class InvestigationDataPort(Protocol):
    """Auth-bound data access for investigation. Employee IDs come only from auth."""

    async def list_available_payslip_periods(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        include_unpublished: bool = False,
    ) -> set[str]:
        """Return period keys YYYY-MM for payslip documents owned by the employee."""
        ...

    async def load_period_snapshot(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period: PeriodRef,
        include_unpublished: bool = False,
    ) -> PeriodSnapshot | None:
        ...

    async def enrich_snapshot_from_original(
        self,
        snapshot: PeriodSnapshot,
        *,
        missing_keys: tuple[str, ...],
    ) -> PeriodSnapshot:
        """Ephemeral S3→OCR→parse for missing keys. Must NOT write to DynamoDB."""
        ...


class InvestigationRunnerPort(ABC):
    @abstractmethod
    async def run(
        self,
        *,
        message: str,
        session_id: str,
        locale: str,
        organization_id: UUID,
        employee_id: UUID,
        include_unpublished: bool = False,
        target_year: int | None = None,
        target_month: int | None = None,
    ) -> InvestigationResult:
        ...
