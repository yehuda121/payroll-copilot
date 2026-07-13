"""Employee profile overview — document collections and monthly expectations.

Never fabricates documents. Missing means missing.
"""

from __future__ import annotations

from calendar import month_name
from datetime import date
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import AuditLogRepository, EmployeeRepository
from payroll_copilot.application.use_cases.manage_employees import (
    EmployeeNotFoundError,
    serialize_employee,
)
from payroll_copilot.domain.document_types import (
    ExpectedDocumentAvailability,
    list_document_types,
)
from payroll_copilot.domain.validation_modules import list_validation_modules


class BuildEmployeeProfileUseCase:
    def __init__(
        self,
        employees: EmployeeRepository,
        audit_logs: AuditLogRepository,
    ) -> None:
        self._employees = employees
        self._audit_logs = audit_logs

    async def execute(self, organization_id: UUID, employee_number: str) -> dict[str, Any]:
        employee = await self._employees.get_by_number(organization_id, employee_number)
        if employee is None:
            raise EmployeeNotFoundError()

        document_types = list_document_types()
        collections: dict[str, dict[str, Any]] = {}
        for doc_type in document_types:
            bucket = collections.setdefault(
                doc_type.collection_key,
                {
                    "key": doc_type.collection_key,
                    "label": doc_type.collection_key.replace("_", " ").title(),
                    "items": [],
                },
            )
            bucket["items"].append(
                {
                    "type_key": doc_type.key,
                    "label": doc_type.label,
                    "availability": ExpectedDocumentAvailability.MISSING.value,
                    "supports_period": doc_type.supports_period,
                    "supports_ocr": doc_type.supports_ocr,
                    "supports_parser": doc_type.supports_parser,
                    "supports_validation_modules": list(doc_type.supports_validation_modules),
                }
            )

        monthly = self._build_monthly_expectations()
        audit_rows = await self._audit_logs.list_recent(organization_id=organization_id, limit=200)
        employee_audit = [
            {
                "id": row.id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": str(row.resource_id) if row.resource_id else None,
                "details": row.details,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in audit_rows
            if row.resource_type == "employee"
            and (
                (row.resource_id and str(row.resource_id) == str(employee.id))
                or row.details.get("employee_number") == employee.employee_number
            )
        ]

        return {
            "employee": serialize_employee(employee),
            "document_collections": list(collections.values()),
            "validation_modules": [
                {
                    "key": module.key,
                    "label": module.label,
                    "description": module.description,
                    "enabled": module.enabled,
                }
                for module in list_validation_modules()
            ],
            "monthly_history": monthly,
            "validation_history": [],
            "findings": [],
            "timeline": employee_audit,
            "audit_log": employee_audit,
        }

    @staticmethod
    def _build_monthly_expectations(*, months: int = 12) -> list[dict[str, Any]]:
        """Expected period slots for the last N months — documents remain missing until uploaded."""
        today = date.today()
        year, month = today.year, today.month
        rows: list[dict[str, Any]] = []
        for _ in range(months):
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "label": f"{month_name[month]} {year}",
                    "payslip": ExpectedDocumentAvailability.MISSING.value,
                    "attendance": ExpectedDocumentAvailability.MISSING.value,
                    "validation_status": "not_run",
                    "missing_documents": ["payslip", "attendance"],
                    "warnings": [],
                }
            )
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        return rows
