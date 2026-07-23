"""AnalyticsService — facade over registered metric use cases.

Future analytics: implement a use case (with metric_name), register it, add a route.
Do not grow a switch of metric names inside this service.
"""

from __future__ import annotations

from uuid import UUID

from payroll_copilot.application.dto.analytics import (
    AdminOrgCensus,
    AdminQualityAnalytics,
    EmployeeSalaryAnalytics,
    OrgPayrollAnalytics,
    OrgQualityAnalytics,
)
from payroll_copilot.application.services.analytics.registry import (
    AnalyticsContext,
    AnalyticsRegistry,
)
from payroll_copilot.application.use_cases.analytics_admin_census import GetAdminOrgCensusUseCase
from payroll_copilot.application.use_cases.analytics_admin_quality import (
    GetAdminQualityAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_employee_salary import (
    GetEmployeeSalaryAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_org_payroll import GetOrgPayrollAnalyticsUseCase
from payroll_copilot.application.use_cases.analytics_org_quality import GetOrgQualityAnalyticsUseCase


class AnalyticsService:
    def __init__(
        self,
        *,
        employee_salary: GetEmployeeSalaryAnalyticsUseCase,
        org_payroll: GetOrgPayrollAnalyticsUseCase,
        admin_census: GetAdminOrgCensusUseCase,
        org_quality: GetOrgQualityAnalyticsUseCase,
        admin_quality: GetAdminQualityAnalyticsUseCase,
        registry: AnalyticsRegistry | None = None,
    ) -> None:
        self._employee_salary = employee_salary
        self._org_payroll = org_payroll
        self._admin_census = admin_census
        self._org_quality = org_quality
        self._admin_quality = admin_quality
        self._registry = registry or AnalyticsRegistry()
        for provider in (
            employee_salary,
            org_payroll,
            admin_census,
            org_quality,
            admin_quality,
        ):
            if provider.metric_name not in self._registry.names():
                self._registry.register(provider)

    @property
    def registry(self) -> AnalyticsRegistry:
        return self._registry

    async def run_metric(self, metric_name: str, context: AnalyticsContext):
        """Generic extension point for future metrics."""
        return await self._registry.compute(metric_name, context)

    async def employee_salary(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        year: int,
        include_unpublished: bool = False,
    ) -> EmployeeSalaryAnalytics:
        return await self._employee_salary.execute(
            organization_id=organization_id,
            employee_id=employee_id,
            year=year,
            include_unpublished=include_unpublished,
        )

    async def org_payroll(
        self,
        *,
        organization_id: UUID,
        year: int,
    ) -> OrgPayrollAnalytics:
        return await self._org_payroll.execute(
            organization_id=organization_id,
            year=year,
        )

    async def admin_census(
        self,
        *,
        organization_ids: list[UUID] | None = None,
    ) -> AdminOrgCensus:
        return await self._admin_census.execute(organization_ids=organization_ids)

    async def org_quality(
        self,
        *,
        organization_id: UUID,
        year: int,
    ) -> OrgQualityAnalytics:
        return await self._org_quality.execute(
            organization_id=organization_id,
            year=year,
        )

    async def admin_quality(self, *, year: int) -> AdminQualityAnalytics:
        return await self._admin_quality.execute(year=year)
