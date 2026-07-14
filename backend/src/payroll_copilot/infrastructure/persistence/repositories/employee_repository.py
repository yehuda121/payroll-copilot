"""SQLAlchemy employee repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus
from payroll_copilot.infrastructure.persistence.mappers.employee_mapper import (
    employee_to_entity,
    employee_to_model,
)
from payroll_copilot.infrastructure.persistence.models import EmployeeModel


class SqlAlchemyEmployeeRepository(EmployeeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, employee_id: UUID) -> Employee | None:
        result = await self._session.execute(
            select(EmployeeModel).where(EmployeeModel.id == employee_id)
        )
        model = result.scalar_one_or_none()
        return employee_to_entity(model) if model else None

    async def get_by_number(self, organization_id: UUID, employee_number: str) -> Employee | None:
        result = await self._session.execute(
            select(EmployeeModel).where(
                EmployeeModel.organization_id == organization_id,
                EmployeeModel.employee_number == employee_number,
            )
        )
        model = result.scalar_one_or_none()
        return employee_to_entity(model) if model else None

    async def get_by_national_id_hash(
        self, organization_id: UUID, national_id_hash: str
    ) -> Employee | None:
        result = await self._session.execute(
            select(EmployeeModel).where(EmployeeModel.organization_id == organization_id)
        )
        for model in result.scalars().all():
            meta = model.metadata_ or {}
            if meta.get("national_id_hash") == national_id_hash:
                return employee_to_entity(model)
        return None

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        stmt = select(EmployeeModel).where(
            EmployeeModel.organization_id == filters.organization_id
        )
        if filters.status is not None:
            stmt = stmt.where(EmployeeModel.status == filters.status)
        elif not filters.include_disabled:
            stmt = stmt.where(EmployeeModel.status != EmployeeStatus.DISABLED)
        if filters.department_id is not None:
            stmt = stmt.where(EmployeeModel.department_id == filters.department_id)
        if filters.query:
            needle = f"%{filters.query.strip()}%"
            stmt = stmt.where(
                or_(
                    EmployeeModel.employee_number.ilike(needle),
                    EmployeeModel.first_name.ilike(needle),
                    EmployeeModel.last_name.ilike(needle),
                )
            )
        stmt = (
            stmt.order_by(EmployeeModel.last_name, EmployeeModel.first_name)
            .offset(max(0, filters.offset))
            .limit(min(max(1, filters.limit), 500))
        )
        result = await self._session.execute(stmt)
        return [employee_to_entity(model) for model in result.scalars().all()]

    async def save(self, employee: Employee) -> Employee:
        result = await self._session.execute(
            select(EmployeeModel).where(EmployeeModel.id == employee.id)
        )
        existing = result.scalar_one_or_none()
        national_id_encrypted = existing.national_id_encrypted if existing else None
        if existing is None:
            model = employee_to_model(employee, national_id_encrypted=None)
            self._session.add(model)
        else:
            existing.employee_number = employee.employee_number
            existing.first_name = employee.first_name
            existing.last_name = employee.last_name
            existing.department_id = employee.department_id
            existing.employment_type = employee.employment_type
            existing.salary_type = employee.salary_type
            existing.hourly_rate = employee.hourly_rate
            existing.monthly_salary = employee.monthly_salary
            existing.contract_start_date = employee.contract_start_date
            existing.contract_end_date = employee.contract_end_date
            existing.manager_id = employee.manager_id
            existing.status = employee.status
            existing.metadata_ = dict(employee.metadata or {})
            if national_id_encrypted is not None:
                existing.national_id_encrypted = national_id_encrypted
        await self._session.flush()
        return employee

    async def save_with_national_id(
        self,
        employee: Employee,
        *,
        national_id_encrypted: bytes | None,
    ) -> Employee:
        result = await self._session.execute(
            select(EmployeeModel).where(EmployeeModel.id == employee.id)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            self._session.add(
                employee_to_model(employee, national_id_encrypted=national_id_encrypted)
            )
        else:
            existing.employee_number = employee.employee_number
            existing.first_name = employee.first_name
            existing.last_name = employee.last_name
            existing.department_id = employee.department_id
            existing.employment_type = employee.employment_type
            existing.salary_type = employee.salary_type
            existing.hourly_rate = employee.hourly_rate
            existing.monthly_salary = employee.monthly_salary
            existing.contract_start_date = employee.contract_start_date
            existing.contract_end_date = employee.contract_end_date
            existing.manager_id = employee.manager_id
            existing.status = employee.status
            existing.metadata_ = dict(employee.metadata or {})
            if national_id_encrypted is not None:
                existing.national_id_encrypted = national_id_encrypted
        await self._session.flush()
        return employee

    async def get_national_id_encrypted(self, employee_id: UUID) -> bytes | None:
        result = await self._session.execute(
            select(EmployeeModel.national_id_encrypted).where(EmployeeModel.id == employee_id)
        )
        return result.scalar_one_or_none()

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Employee]:
        result = await self._session.execute(select(EmployeeModel))
        matched: list[Employee] = []
        for model in result.scalars().all():
            meta = model.metadata_ or {}
            if meta.get("dataset_id") == dataset_id:
                matched.append(employee_to_entity(model))
        return matched

    async def delete_by_ids(self, employee_ids: list[UUID]) -> int:
        if not employee_ids:
            return 0
        result = await self._session.execute(
            delete(EmployeeModel).where(EmployeeModel.id.in_(employee_ids))
        )
        await self._session.flush()
        return int(result.rowcount or 0)
