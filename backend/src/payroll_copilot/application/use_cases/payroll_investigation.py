"""Payroll investigation use case — auth-bound command → investigation graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from payroll_copilot.application.ports.investigation import InvestigationRunnerPort
from payroll_copilot.domain.investigation.types import InvestigationResult


@dataclass(frozen=True, slots=True)
class PayrollInvestigationCommand:
    message: str
    organization_id: UUID
    employee_id: UUID
    session_id: str | None = None
    locale: str = "he"
    include_unpublished: bool = False
    target_year: int | None = None
    target_month: int | None = None


class PayrollInvestigationUseCase:
    """Runs the investigation graph with backend-derived employee binding only."""

    def __init__(self, runner: InvestigationRunnerPort) -> None:
        self._runner = runner

    async def execute(self, command: PayrollInvestigationCommand) -> InvestigationResult:
        session_id = command.session_id or str(uuid4())
        return await self._runner.run(
            message=command.message,
            session_id=session_id,
            locale=command.locale,
            organization_id=command.organization_id,
            employee_id=command.employee_id,
            include_unpublished=command.include_unpublished,
            target_year=command.target_year,
            target_month=command.target_month,
        )
