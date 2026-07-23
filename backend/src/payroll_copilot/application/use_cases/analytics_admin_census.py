"""Admin organization census using employees + user bindings + org directory."""

from __future__ import annotations

from collections import Counter
from typing import Protocol
from uuid import UUID

from payroll_copilot.application.dto.analytics import (
    AdminOrgCensus,
    AccountantCaseload,
    OrganizationCensusSlice,
)
from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.application.ports.organization_directory import OrganizationDirectoryPort
from payroll_copilot.domain.enums import UserRole


class UserDirectoryPort(Protocol):
    """Structural protocol for listing org-scoped user bindings."""

    async def list_for_organization(self, organization_id: UUID) -> list: ...


class GetAdminOrgCensusUseCase:
    """Companies / employees / payroll accountants and assignment stats."""

    metric_name = "admin.census"

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        users: UserDirectoryPort,
        organizations: OrganizationDirectoryPort,
    ) -> None:
        self._employees = employees
        self._users = users
        self._organizations = organizations

    async def execute(
        self,
        *,
        organization_ids: list[UUID] | None = None,
    ) -> AdminOrgCensus:
        org_ids = list(organization_ids) if organization_ids is not None else []
        if not org_ids:
            org_ids = await self._organizations.list_organization_ids()

        slices: list[OrganizationCensusSlice] = []
        total_employees = 0
        total_accountants = 0
        total_unassigned = 0
        global_caseload: Counter[UUID] = Counter()

        for org_id in org_ids:
            employees = await self._employees.list(
                EmployeeListFilter(organization_id=org_id, limit=10_000, offset=0)
            )
            users = await self._users.list_for_organization(org_id)
            accountants = [
                u
                for u in users
                if getattr(u, "role", None) == UserRole.ACCOUNTANT
                or str(getattr(getattr(u, "role", None), "value", getattr(u, "role", "")))
                == UserRole.ACCOUNTANT.value
            ]
            unassigned = sum(1 for e in employees if e.payroll_accountant_id is None)
            caseload_counter: Counter[UUID] = Counter(
                e.payroll_accountant_id
                for e in employees
                if e.payroll_accountant_id is not None
            )
            caseload = [
                AccountantCaseload(payroll_accountant_id=aid, employee_count=count)
                for aid, count in sorted(caseload_counter.items(), key=lambda x: (-x[1], str(x[0])))
            ]
            for aid, count in caseload_counter.items():
                global_caseload[aid] += count

            slices.append(
                OrganizationCensusSlice(
                    organization_id=org_id,
                    employees_count=len(employees),
                    payroll_accountants_count=len(accountants),
                    employees_without_payroll_accountant=unassigned,
                    employees_per_payroll_accountant=caseload,
                )
            )
            total_employees += len(employees)
            total_accountants += len(accountants)
            total_unassigned += unassigned

        return AdminOrgCensus(
            companies_count=len(org_ids),
            employees_count=total_employees,
            payroll_accountants_count=total_accountants,
            employees_without_payroll_accountant=total_unassigned,
            employees_per_payroll_accountant=[
                AccountantCaseload(payroll_accountant_id=aid, employee_count=count)
                for aid, count in sorted(global_caseload.items(), key=lambda x: (-x[1], str(x[0])))
            ],
            organizations=slices,
        )

    async def compute(self, context):
        org_ids = context.params.get("organization_ids")
        if org_ids is None and context.organization_id is not None:
            # Optional single-org focus when explicitly requested via params flag.
            if context.params.get("scope_to_principal_org"):
                org_ids = [context.organization_id]
        return await self.execute(organization_ids=org_ids)
