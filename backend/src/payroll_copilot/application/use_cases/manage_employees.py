"""Employee master-data use cases (separate from User authentication)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRepository,
    EmployeeListFilter,
    EmployeeRepository,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)
from payroll_copilot.infrastructure.security.field_crypto import (
    encrypt_national_id,
    hash_national_id,
    mask_national_id,
)


class EmployeeConflictError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EmployeeNotFoundError(Exception):
    def __init__(self, message: str = "Employee not found.") -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CreateEmployeeCommand:
    organization_id: UUID
    employee_number: str
    first_name: str
    last_name: str
    department_id: UUID
    employment_type: EmploymentType
    salary_type: SalaryType
    contract_start_date: date
    actor_user_id: UUID | None = None
    national_id: str | None = None
    email: str | None = None
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    contract_end_date: date | None = None
    profile_incomplete: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class UpdateEmployeeCommand:
    organization_id: UUID
    employee_number: str
    actor_user_id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    department_id: UUID | None = None
    employment_type: EmploymentType | None = None
    salary_type: SalaryType | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    national_id: str | None = None
    email: str | None = None
    status: EmployeeStatus | None = None
    profile_incomplete: bool | None = None
    metadata: dict[str, Any] | None = None


def serialize_employee(employee: Employee) -> dict[str, Any]:
    meta = dict(employee.metadata or {})
    rate = employee.monthly_salary if employee.salary_type == SalaryType.MONTHLY else employee.hourly_rate
    display_name = meta.get("verified_display_name") or employee.full_name
    return {
        "id": str(employee.id),
        "organization_id": str(employee.organization_id),
        "employee_number": employee.employee_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "full_name": display_name,
        "email": meta.get("email"),
        "department_id": str(employee.department_id),
        "department": meta.get("department_label") or meta.get("department") or "General",
        "employment_type": employee.employment_type.value,
        "salary_type": employee.salary_type.value,
        "base_salary_or_rate": float(rate) if rate is not None else None,
        "hourly_rate": float(employee.hourly_rate) if employee.hourly_rate is not None else None,
        "monthly_salary": float(employee.monthly_salary) if employee.monthly_salary is not None else None,
        "contract_start_date": employee.contract_start_date.isoformat(),
        "contract_end_date": employee.contract_end_date.isoformat() if employee.contract_end_date else None,
        "status": employee.status.value,
        "profile_incomplete": bool(meta.get("profile_incomplete", False)),
        "national_id_masked": meta.get("national_id_masked"),
        "metadata": {
            key: value
            for key, value in meta.items()
            if key not in {"national_id_hash"}
        },
    }


class ManageEmployeesUseCase:
    def __init__(
        self,
        employees: EmployeeRepository,
        audit_logs: AuditLogRepository,
        *,
        encryption_key: str,
    ) -> None:
        self._employees = employees
        self._audit = audit_logs
        self._encryption_key = encryption_key

    async def list_employees(self, filters: EmployeeListFilter) -> list[dict[str, Any]]:
        rows = await self._employees.list(filters)
        return [serialize_employee(row) for row in rows]

    async def get_by_number(self, organization_id: UUID, employee_number: str) -> dict[str, Any]:
        employee = await self._employees.get_by_number(organization_id, employee_number)
        if employee is None:
            raise EmployeeNotFoundError()
        return serialize_employee(employee)

    async def create(self, command: CreateEmployeeCommand) -> dict[str, Any]:
        existing = await self._employees.get_by_number(
            command.organization_id, command.employee_number.strip()
        )
        if existing is not None:
            raise EmployeeConflictError("Employee number already exists in this organization.")

        metadata = dict(command.metadata or {})
        if command.email:
            metadata["email"] = command.email.strip()
        metadata["profile_incomplete"] = bool(command.profile_incomplete)

        encrypted: bytes | None = None
        if command.national_id and command.national_id.strip():
            nid = command.national_id.strip()
            nid_hash = hash_national_id(nid)
            conflict = await self._employees.get_by_national_id_hash(
                command.organization_id, nid_hash
            )
            if conflict is not None:
                raise EmployeeConflictError("An employee with this national ID already exists.")
            metadata["national_id_hash"] = nid_hash
            metadata["national_id_masked"] = mask_national_id(nid)
            encrypted = encrypt_national_id(nid, encryption_key=self._encryption_key)

        employee = Employee(
            id=uuid4(),
            organization_id=command.organization_id,
            employee_number=command.employee_number.strip(),
            first_name=command.first_name.strip(),
            last_name=command.last_name.strip(),
            department_id=command.department_id,
            employment_type=command.employment_type,
            salary_type=command.salary_type,
            contract_start_date=command.contract_start_date,
            status=EmployeeStatus.ACTIVE,
            hourly_rate=command.hourly_rate,
            monthly_salary=command.monthly_salary,
            contract_end_date=command.contract_end_date,
            metadata=metadata,
        )

        if isinstance(self._employees, SqlAlchemyEmployeeRepository):
            await self._employees.save_with_national_id(
                employee, national_id_encrypted=encrypted
            )
        else:
            await self._employees.save(employee)

        await self._audit.append(
            AuditLogEntry(
                action="employee.created",
                resource_type="employee",
                resource_id=employee.id,
                organization_id=command.organization_id,
                user_id=command.actor_user_id,
                details={
                    "employee_number": employee.employee_number,
                    "profile_incomplete": metadata.get("profile_incomplete", False),
                },
            )
        )
        return serialize_employee(employee)

    async def update(self, command: UpdateEmployeeCommand) -> dict[str, Any]:
        employee = await self._employees.get_by_number(
            command.organization_id, command.employee_number
        )
        if employee is None:
            raise EmployeeNotFoundError()

        metadata = dict(employee.metadata or {})
        encrypted: bytes | None = None

        if command.first_name is not None:
            employee.first_name = command.first_name.strip()
        if command.last_name is not None:
            employee.last_name = command.last_name.strip()
        if command.department_id is not None:
            employee.department_id = command.department_id
        if command.employment_type is not None:
            employee.employment_type = command.employment_type
        if command.salary_type is not None:
            employee.salary_type = command.salary_type
        if command.contract_start_date is not None:
            employee.contract_start_date = command.contract_start_date
        if command.contract_end_date is not None:
            employee.contract_end_date = command.contract_end_date
        if command.hourly_rate is not None:
            employee.hourly_rate = command.hourly_rate
        if command.monthly_salary is not None:
            employee.monthly_salary = command.monthly_salary
        if command.status is not None:
            employee.status = command.status
        if command.email is not None:
            metadata["email"] = command.email.strip()
        if command.profile_incomplete is not None:
            metadata["profile_incomplete"] = command.profile_incomplete
        if command.metadata:
            metadata.update(command.metadata)
        if command.national_id is not None and command.national_id.strip():
            nid = command.national_id.strip()
            nid_hash = hash_national_id(nid)
            conflict = await self._employees.get_by_national_id_hash(
                command.organization_id, nid_hash
            )
            if conflict is not None and conflict.id != employee.id:
                raise EmployeeConflictError("An employee with this national ID already exists.")
            metadata["national_id_hash"] = nid_hash
            metadata["national_id_masked"] = mask_national_id(nid)
            encrypted = encrypt_national_id(nid, encryption_key=self._encryption_key)

        employee.metadata = metadata

        if isinstance(self._employees, SqlAlchemyEmployeeRepository):
            await self._employees.save_with_national_id(
                employee, national_id_encrypted=encrypted
            )
        else:
            await self._employees.save(employee)

        await self._audit.append(
            AuditLogEntry(
                action="employee.updated",
                resource_type="employee",
                resource_id=employee.id,
                organization_id=command.organization_id,
                user_id=command.actor_user_id,
                details={"employee_number": employee.employee_number, "status": employee.status.value},
            )
        )
        return serialize_employee(employee)

    async def disable(self, organization_id: UUID, employee_number: str, *, actor_user_id: UUID | None) -> dict[str, Any]:
        return await self.update(
            UpdateEmployeeCommand(
                organization_id=organization_id,
                employee_number=employee_number,
                actor_user_id=actor_user_id,
                status=EmployeeStatus.DISABLED,
            )
        )

    async def match_by_national_id(
        self, organization_id: UUID, national_id: str
    ) -> dict[str, Any] | None:
        employee = await self._employees.get_by_national_id_hash(
            organization_id, hash_national_id(national_id)
        )
        return serialize_employee(employee) if employee else None
