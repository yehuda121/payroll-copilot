"""Map between Employee domain entity and SQLAlchemy model."""

from __future__ import annotations

from payroll_copilot.domain.entities import Employee
from payroll_copilot.infrastructure.persistence.models import EmployeeModel


def employee_to_entity(model: EmployeeModel) -> Employee:
    return Employee(
        id=model.id,
        organization_id=model.organization_id,
        employee_number=model.employee_number,
        first_name=model.first_name,
        last_name=model.last_name,
        department_id=model.department_id,
        employment_type=model.employment_type,
        salary_type=model.salary_type,
        contract_start_date=model.contract_start_date,
        status=model.status,
        hourly_rate=model.hourly_rate,
        monthly_salary=model.monthly_salary,
        contract_end_date=model.contract_end_date,
        manager_id=model.manager_id,
        metadata=dict(model.metadata_ or {}),
    )


def employee_to_model(employee: Employee, *, national_id_encrypted: bytes | None = None) -> EmployeeModel:
    return EmployeeModel(
        id=employee.id,
        organization_id=employee.organization_id,
        employee_number=employee.employee_number,
        national_id_encrypted=national_id_encrypted,
        first_name=employee.first_name,
        last_name=employee.last_name,
        department_id=employee.department_id,
        employment_type=employee.employment_type,
        salary_type=employee.salary_type,
        hourly_rate=employee.hourly_rate,
        monthly_salary=employee.monthly_salary,
        contract_start_date=employee.contract_start_date,
        contract_end_date=employee.contract_end_date,
        manager_id=employee.manager_id,
        status=employee.status,
        metadata_=dict(employee.metadata or {}),
    )
