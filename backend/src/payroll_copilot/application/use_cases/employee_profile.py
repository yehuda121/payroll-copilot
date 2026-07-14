"""Employee profile overview — document collections and monthly expectations.

Never fabricates documents. Missing means missing.
Payslip availability is derived from persisted documents only.
"""

from __future__ import annotations

from calendar import month_name
from datetime import date
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import AuditLogRepository, EmployeeRepository
from payroll_copilot.application.ports.repositories import DocumentRepository
from payroll_copilot.application.use_cases.manage_employees import (
    EmployeeNotFoundError,
    serialize_employee,
)
from payroll_copilot.domain.document_types import (
    ExpectedDocumentAvailability,
    list_document_types,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.domain.validation_modules import list_validation_modules


class BuildEmployeeProfileUseCase:
    def __init__(
        self,
        employees: EmployeeRepository,
        audit_logs: AuditLogRepository,
        documents: DocumentRepository | None = None,
    ) -> None:
        self._employees = employees
        self._audit_logs = audit_logs
        self._documents = documents

    async def execute(self, organization_id: UUID, employee_number: str) -> dict[str, Any]:
        employee = await self._employees.get_by_number(organization_id, employee_number)
        if employee is None:
            raise EmployeeNotFoundError()

        docs: list[Any] = []
        if self._documents is not None:
            docs = await self._documents.list_for_employee(
                organization_id=organization_id,
                employee_id=employee.id,
            )

        payslips = [doc for doc in docs if doc.document_type == DocumentType.PAYSLIP]
        attendance_docs = [doc for doc in docs if doc.document_type == DocumentType.ATTENDANCE]
        contract_docs = [doc for doc in docs if doc.document_type == DocumentType.CONTRACT]
        identity_docs = [doc for doc in docs if doc.document_type == DocumentType.NATIONAL_ID]
        appendix_docs = [doc for doc in docs if doc.document_type == DocumentType.ID_APPENDIX]

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
            related = {
                "payslip": payslips,
                "attendance": attendance_docs,
                "contract": contract_docs,
                "national_id": identity_docs,
                "id_appendix": appendix_docs,
            }.get(doc_type.key, [])

            if not related:
                bucket["items"].append(
                    {
                        "type_key": doc_type.key,
                        "label": doc_type.label,
                        "availability": ExpectedDocumentAvailability.MISSING.value,
                        "supports_period": doc_type.supports_period,
                        "supports_ocr": doc_type.supports_ocr,
                        "supports_parser": doc_type.supports_parser,
                        "supports_validation_modules": list(doc_type.supports_validation_modules),
                        "documents": [],
                    }
                )
                continue

            for doc in related:
                meta = dict(doc.metadata or {})
                period = doc.period
                bucket["items"].append(
                    {
                        "type_key": doc_type.key,
                        "label": doc_type.label,
                        "availability": ExpectedDocumentAvailability.AVAILABLE.value,
                        "supports_period": doc_type.supports_period,
                        "supports_ocr": doc_type.supports_ocr,
                        "supports_parser": doc_type.supports_parser,
                        "supports_validation_modules": list(doc_type.supports_validation_modules),
                        "document_id": str(doc.id),
                        "period_year": period.year if period else None,
                        "period_month": period.month if period else None,
                        "fixture_classification": meta.get("fixture_classification"),
                        "source_page": meta.get("source_page"),
                        "fixture_path": meta.get("fixture_path"),
                        "gross_salary": meta.get("gross_salary"),
                        "net_salary": meta.get("net_salary"),
                    }
                )

        monthly = self._build_monthly_expectations(payslips=payslips, attendance_docs=attendance_docs)
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
    def _build_monthly_expectations(
        *,
        payslips: list[Any],
        attendance_docs: list[Any],
        months: int = 12,
    ) -> list[dict[str, Any]]:
        payslip_periods = {
            (doc.period.year, doc.period.month)
            for doc in payslips
            if doc.period is not None
        }
        attendance_periods = {
            (doc.period.year, doc.period.month)
            for doc in attendance_docs
            if doc.period is not None
        }

        today = date.today()
        year, month = today.year, today.month
        period_slots: list[tuple[int, int]] = []
        for _ in range(months):
            period_slots.append((year, month))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        for period in payslip_periods | attendance_periods:
            if period not in period_slots:
                period_slots.append(period)
        period_slots = sorted(set(period_slots), reverse=True)

        rows: list[dict[str, Any]] = []
        for year, month in period_slots:
            has_payslip = (year, month) in payslip_periods
            has_attendance = (year, month) in attendance_periods
            missing: list[str] = []
            if not has_payslip:
                missing.append("payslip")
            if not has_attendance:
                missing.append("attendance")
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "label": f"{month_name[month]} {year}",
                    "payslip": (
                        ExpectedDocumentAvailability.AVAILABLE.value
                        if has_payslip
                        else ExpectedDocumentAvailability.MISSING.value
                    ),
                    "attendance": (
                        ExpectedDocumentAvailability.AVAILABLE.value
                        if has_attendance
                        else ExpectedDocumentAvailability.MISSING.value
                    ),
                    "validation_status": "not_run",
                    "missing_documents": missing,
                    "warnings": [],
                }
            )
        return rows
