"""DynamoDB employee repository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, GSI2, GSI3, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    b64_to_bytes,
    bytes_to_b64,
    dumps_value,
    loads_date,
    loads_decimal,
    loads_uuid,
)


class DynamoEmployeeRepository(EmployeeRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _to_item(
        self,
        employee: Employee,
        *,
        national_id_encrypted: bytes | None,
    ) -> dict:
        meta = dict(employee.metadata or {})
        nid_hash = meta.get("national_id_hash")
        dataset_id = meta.get("dataset_id")
        now = datetime.now(UTC).isoformat()
        item: dict = {
            "PK": keys.org_pk(employee.organization_id),
            "SK": keys.emp_sk(employee.id),
            "entity_type": "employee",
            "GSI1PK": keys.gsi1_emp(employee.id),
            "GSI1SK": keys.org_pk(employee.organization_id),
            "GSI2PK": keys.gsi2_emp_number(employee.organization_id, employee.employee_number),
            "GSI2SK": keys.emp_sk(employee.id),
            "id": str(employee.id),
            "organization_id": str(employee.organization_id),
            "employee_number": employee.employee_number,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "department_id": dumps_value(employee.department_id),
            "employment_type": dumps_value(employee.employment_type),
            "salary_type": dumps_value(employee.salary_type),
            "hourly_rate": dumps_value(employee.hourly_rate),
            "monthly_salary": dumps_value(employee.monthly_salary),
            "contract_start_date": dumps_value(employee.contract_start_date),
            "contract_end_date": dumps_value(employee.contract_end_date),
            "manager_id": dumps_value(employee.manager_id),
            "payroll_accountant_id": dumps_value(employee.payroll_accountant_id),
            "status": dumps_value(employee.status),
            "metadata": dumps_value(meta),
            "national_id_encrypted_b64": bytes_to_b64(national_id_encrypted),
            "updated_at": now,
        }
        if nid_hash:
            item["GSI3PK"] = keys.gsi2_national_id(employee.organization_id, str(nid_hash))
            item["GSI3SK"] = keys.emp_sk(employee.id)
        if dataset_id:
            item["dataset_id"] = str(dataset_id)
        return {k: v for k, v in item.items() if v is not None}

    async def _put_dataset_pointer(self, employee: Employee) -> None:
        dataset_id = (employee.metadata or {}).get("dataset_id")
        if not dataset_id:
            return
        await self._table.put_item(
            {
                "PK": keys.gsi3_dataset(str(dataset_id)),
                "SK": keys.emp_sk(employee.id),
                "entity_type": "dataset_employee",
                "employee_id": str(employee.id),
                "organization_id": str(employee.organization_id),
            }
        )

    def _to_entity(self, item: dict) -> Employee:
        department_id = loads_uuid(item.get("department_id"))
        if department_id is None:
            department_id = UUID(int=0)
        return Employee(
            id=UUID(str(item["id"])),
            organization_id=UUID(str(item["organization_id"])),
            employee_number=str(item.get("employee_number") or ""),
            first_name=str(item.get("first_name") or ""),
            last_name=str(item.get("last_name") or ""),
            department_id=department_id,
            employment_type=EmploymentType(str(item.get("employment_type") or EmploymentType.FULL_TIME.value)),
            salary_type=SalaryType(str(item.get("salary_type") or SalaryType.MONTHLY.value)),
            contract_start_date=loads_date(item.get("contract_start_date")) or date(1970, 1, 1),
            status=EmployeeStatus(str(item.get("status") or EmployeeStatus.ACTIVE.value)),
            hourly_rate=loads_decimal(item.get("hourly_rate")),
            monthly_salary=loads_decimal(item.get("monthly_salary")),
            contract_end_date=loads_date(item.get("contract_end_date")),
            manager_id=loads_uuid(item.get("manager_id")),
            payroll_accountant_id=loads_uuid(item.get("payroll_accountant_id")),
            metadata=dict(item.get("metadata") or {}),
        )

    async def get_by_id(self, employee_id: UUID) -> Employee | None:
        items = await self._table.query_eq_pk(keys.gsi1_emp(employee_id), index_name=GSI1, limit=10)
        for item in items:
            if item.get("entity_type") == "employee" and item.get("id"):
                return self._to_entity(item)
        return None

    async def get_by_number(self, organization_id: UUID, employee_number: str) -> Employee | None:
        items = await self._table.query_eq_pk(
            keys.gsi2_emp_number(organization_id, employee_number),
            index_name=GSI2,
            limit=10,
        )
        for item in items:
            if item.get("entity_type") == "employee" and item.get("id"):
                return self._to_entity(item)
        return None

    async def get_by_national_id_hash(
        self, organization_id: UUID, national_id_hash: str
    ) -> Employee | None:
        items = await self._table.query_eq_pk(
            keys.gsi2_national_id(organization_id, national_id_hash),
            index_name=GSI3,
            limit=1,
        )
        if items:
            return self._to_entity(items[0])
        # Fallback: scan org employees (sparse GSI3 may be used for dataset instead).
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="EMP#",
        )
        for item in items:
            meta = item.get("metadata") or {}
            if meta.get("national_id_hash") == national_id_hash:
                return self._to_entity(item)
        return None

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        items = await self._table.query_eq_pk(
            keys.org_pk(filters.organization_id),
            sk_begins_with="EMP#",
        )
        employees = [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "employee" and item.get("id")
        ]
        if filters.status is not None:
            employees = [e for e in employees if e.status == filters.status]
        elif not filters.include_disabled:
            employees = [e for e in employees if e.status != EmployeeStatus.DISABLED]
        if filters.department_id is not None:
            employees = [e for e in employees if e.department_id == filters.department_id]
        if filters.query:
            needle = filters.query.strip().lower()
            employees = [
                e
                for e in employees
                if needle in e.employee_number.lower()
                or needle in e.first_name.lower()
                or needle in e.last_name.lower()
            ]
        employees.sort(key=lambda e: (e.last_name.lower(), e.first_name.lower()))
        start = max(0, filters.offset)
        end = start + min(max(1, filters.limit), 500)
        return employees[start:end]

    async def _load_encrypted(self, employee_id: UUID) -> bytes | None:
        items = await self._table.query_eq_pk(keys.gsi1_emp(employee_id), index_name=GSI1, limit=10)
        for item in items:
            if item.get("entity_type") == "employee":
                return b64_to_bytes(item.get("national_id_encrypted_b64"))
        return None

    async def save(self, employee: Employee) -> Employee:
        encrypted = await self._load_encrypted(employee.id)
        await self._table.put_item(self._to_item(employee, national_id_encrypted=encrypted))
        await self._put_dataset_pointer(employee)
        return employee

    async def save_with_national_id(
        self,
        employee: Employee,
        *,
        national_id_encrypted: bytes | None,
    ) -> Employee:
        existing = await self._load_encrypted(employee.id)
        encrypted = national_id_encrypted if national_id_encrypted is not None else existing
        await self._table.put_item(self._to_item(employee, national_id_encrypted=encrypted))
        await self._put_dataset_pointer(employee)
        return employee

    async def get_national_id_encrypted(self, employee_id: UUID) -> bytes | None:
        return await self._load_encrypted(employee_id)

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Employee]:
        pointers = await self._table.query_eq_pk(keys.gsi3_dataset(dataset_id))
        employees: list[Employee] = []
        for pointer in pointers:
            emp_id = loads_uuid(pointer.get("employee_id"))
            if emp_id is None:
                continue
            employee = await self.get_by_id(emp_id)
            if employee is not None:
                employees.append(employee)
        return employees

    async def delete_by_ids(self, employee_ids: list[UUID]) -> int:
        keys_to_delete: list[dict] = []
        for employee_id in employee_ids:
            items = await self._table.query_eq_pk(
                keys.gsi1_emp(employee_id), index_name=GSI1, limit=1
            )
            for item in items:
                keys_to_delete.append({"PK": item["PK"], "SK": item["SK"]})
                dataset_id = (item.get("metadata") or {}).get("dataset_id") or item.get(
                    "dataset_id"
                )
                if dataset_id:
                    keys_to_delete.append(
                        {"PK": keys.gsi3_dataset(str(dataset_id)), "SK": keys.emp_sk(employee_id)}
                    )
        return await self._table.batch_delete(keys_to_delete)
