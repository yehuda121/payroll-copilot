"""Accountant Portal development seed — load/cleanup verified fixture dataset.

Does not run OCR or AI parsing. Does not fabricate validation findings.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRepository,
    EmployeeRepository,
)
from payroll_copilot.application.ports.repositories import DocumentRepository
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.entities import Document, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
)
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.persistence.models import DocumentExtractionModel
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.workspace_bootstrap import (
    OrganizationWorkspaceBootstrap,
)
from payroll_copilot.infrastructure.security.field_crypto import (
    encrypt_national_id,
    hash_national_id,
    mask_national_id,
)

logger = logging.getLogger(__name__)

DATASET_ID = "accountant_portal_seed_v1"
DATASET_VERSION = "1.0"
SEED_NAMESPACE = uuid5(NAMESPACE_URL, "payroll-copilot:accountant-portal-seed")

_DEFAULT_DATASET_CANDIDATES = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "data" / "accountant_portal_seed.json",
    Path("/app/tests/fixtures/data/accountant_portal_seed.json"),
    Path.cwd() / "tests" / "fixtures" / "data" / "accountant_portal_seed.json",
    Path.cwd() / "backend" / "tests" / "fixtures" / "data" / "accountant_portal_seed.json",
)


class SeedProductionBlockedError(RuntimeError):
    """Raised when seed/cleanup is attempted in a production environment."""


class SeedDatasetError(RuntimeError):
    """Raised when the seed dataset file is missing or invalid."""


def assert_seed_environment_allowed(app_env: str) -> None:
    normalized = (app_env or "").strip().lower()
    if normalized in {"production", "prod"}:
        raise SeedProductionBlockedError(
            f"Accountant portal seed is blocked when APP_ENV={app_env!r}."
        )


def resolve_dataset_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit
        if not path.is_file():
            raise SeedDatasetError(f"Seed dataset not found: {path}")
        return path
    for candidate in _DEFAULT_DATASET_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SeedDatasetError(
        "Seed dataset accountant_portal_seed.json not found in known fixture locations."
    )


def load_dataset(path: Path | None = None) -> dict[str, Any]:
    dataset_path = resolve_dataset_path(path)
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if payload.get("dataset_id") != DATASET_ID:
        raise SeedDatasetError(
            f"Unexpected dataset_id {payload.get('dataset_id')!r}; expected {DATASET_ID!r}."
        )
    return payload


def deterministic_employee_id(national_id: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"employee:{''.join(ch for ch in national_id if ch.isalnum())}")


def deterministic_document_id(document_key: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"document:{document_key}")


def _repo_relative_fixture_path(fixture_path: str, *, repo_root: Path) -> Path:
    relative = fixture_path
    if relative.startswith("backend/"):
        relative = relative[len("backend/") :]
    return repo_root / relative


def _file_fingerprint(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest(), len(content)


@dataclass(frozen=True, slots=True)
class SeedResult:
    dataset_id: str
    dataset_version: str
    employees_upserted: int
    payslips_upserted: int
    employees_total: int
    payslips_total: int


@dataclass(frozen=True, slots=True)
class CleanupResult:
    dataset_id: str
    employees_deleted: int
    payslips_deleted: int
    audit_rows_deleted: int


class SeedAccountantPortalUseCase:
    """Idempotent upsert of the verified accountant portal development seed."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        employees: EmployeeRepository,
        documents: DocumentRepository,
        audit_logs: AuditLogRepository,
        encryption_key: str,
        app_env: str,
        repo_root: Path | None = None,
    ) -> None:
        self._session = session
        self._employees = employees
        self._documents = documents
        self._audit = audit_logs
        self._encryption_key = encryption_key
        self._app_env = app_env
        self._repo_root = repo_root or Path(__file__).resolve().parents[4]

    async def execute(self, dataset_path: Path | None = None) -> SeedResult:
        assert_seed_environment_allowed(self._app_env)
        dataset = load_dataset(dataset_path)
        defaults = dataset.get("unverified_required_schema_defaults") or {}
        sources = {
            item["source_document_key"]: item for item in dataset.get("source_documents") or []
        }

        org_id = DEMO_ORGANIZATION_ID
        bootstrap = OrganizationWorkspaceBootstrap(self._session)
        department_id = await bootstrap.ensure_default_department(org_id)
        await bootstrap.ensure_organization(org_id, name="Demo Organization")

        employees_by_nid: dict[str, Employee] = {}
        upserted_employees = 0
        for row in dataset.get("employees") or []:
            employee, created = await self._upsert_employee(
                org_id=org_id,
                department_id=department_id,
                row=row,
                defaults=defaults,
                dataset=dataset,
            )
            employees_by_nid["".join(ch for ch in str(row["national_id"]) if ch.isalnum())] = (
                employee
            )
            if created:
                upserted_employees += 1
            else:
                upserted_employees += 1  # counts upserts for reporting

        source_fingerprints: dict[str, tuple[str, int, str, str]] = {}
        for key, source in sources.items():
            if source.get("seed_as_payslip") is False:
                continue
            path = _repo_relative_fixture_path(source["fixture_path"], repo_root=self._repo_root)
            if not path.is_file():
                # Docker mounts fixtures at /app/tests/fixtures
                alt = Path("/app") / source["fixture_path"].removeprefix("backend/")
                path = alt if alt.is_file() else path
            if not path.is_file():
                raise SeedDatasetError(f"Fixture PDF missing for seed: {source['fixture_path']}")
            checksum, size = _file_fingerprint(path)
            source_fingerprints[key] = (
                checksum,
                size,
                source["fixture_path"],
                source.get("media_type") or "application/pdf",
            )

        upserted_payslips = 0
        for slip in dataset.get("payslips") or []:
            nid = "".join(ch for ch in str(slip["national_id"]) if ch.isalnum())
            employee = employees_by_nid.get(nid)
            if employee is None:
                raise SeedDatasetError(
                    f"Payslip {slip.get('document_key')} references unknown national_id."
                )
            source_key = slip["source_document_key"]
            if source_key not in source_fingerprints:
                raise SeedDatasetError(f"Unknown or non-seedable source_document_key={source_key}")
            checksum, size, fixture_path, mime = source_fingerprints[source_key]
            await self._upsert_payslip(
                employee=employee,
                slip=slip,
                dataset=dataset,
                checksum=checksum,
                size=size,
                fixture_path=fixture_path,
                mime_type=mime,
            )
            upserted_payslips += 1

        await self._audit.append(
            AuditLogEntry(
                action="seed.applied",
                resource_type="dataset",
                resource_id=None,
                organization_id=org_id,
                details={
                    "dataset_id": dataset["dataset_id"],
                    "dataset_version": dataset.get("dataset_version"),
                    "employees": len(dataset.get("employees") or []),
                    "payslips": len(dataset.get("payslips") or []),
                },
            )
        )

        seeded_employees = await self._employees.list_by_dataset_id(dataset_id=DATASET_ID)
        seeded_docs = await self._documents.list_by_dataset_id(dataset_id=DATASET_ID)
        payslip_docs = [
            doc for doc in seeded_docs if doc.document_type == DocumentType.PAYSLIP
        ]
        return SeedResult(
            dataset_id=DATASET_ID,
            dataset_version=str(dataset.get("dataset_version") or DATASET_VERSION),
            employees_upserted=upserted_employees,
            payslips_upserted=upserted_payslips,
            employees_total=len(seeded_employees),
            payslips_total=len(payslip_docs),
        )

    async def cleanup(self) -> CleanupResult:
        assert_seed_environment_allowed(self._app_env)
        documents = await self._documents.list_by_dataset_id(dataset_id=DATASET_ID)
        document_ids = [doc.id for doc in documents]
        if document_ids:
            await self._session.execute(
                delete(DocumentExtractionModel).where(
                    DocumentExtractionModel.document_id.in_(document_ids)
                )
            )
            await self._session.flush()
        payslips_deleted = await self._documents.delete_by_ids(document_ids)

        employees = await self._employees.list_by_dataset_id(dataset_id=DATASET_ID)
        employee_ids = [emp.id for emp in employees]
        employees_deleted = await self._employees.delete_by_ids(employee_ids)
        audit_deleted = await self._audit.delete_by_dataset_id(dataset_id=DATASET_ID)

        await self._audit.append(
            AuditLogEntry(
                action="seed.cleaned",
                resource_type="dataset",
                resource_id=None,
                organization_id=DEMO_ORGANIZATION_ID,
                details={
                    "dataset_id": DATASET_ID,
                    "employees_deleted": employees_deleted,
                    "payslips_deleted": payslips_deleted,
                    "audit_rows_deleted": audit_deleted,
                },
            )
        )
        # The cleanup audit itself carries dataset_id — leave it for visibility.
        return CleanupResult(
            dataset_id=DATASET_ID,
            employees_deleted=employees_deleted,
            payslips_deleted=payslips_deleted,
            audit_rows_deleted=audit_deleted,
        )

    async def _upsert_employee(
        self,
        *,
        org_id: UUID,
        department_id: UUID,
        row: dict[str, Any],
        defaults: dict[str, Any],
        dataset: dict[str, Any],
    ) -> tuple[Employee, bool]:
        national_id = str(row["national_id"]).strip()
        nid_hash = hash_national_id(national_id)
        existing = await self._employees.get_by_national_id_hash(org_id, nid_hash)
        created = existing is None
        employee_id = existing.id if existing else deterministic_employee_id(national_id)

        employment_raw = row.get("employment_type") or defaults.get("employment_type") or "full_time"
        salary_raw = row.get("salary_type") or defaults.get("salary_type") or "monthly"
        start_raw = row.get("contract_start_date") or defaults.get("contract_start_date")
        contract_start = date.fromisoformat(str(start_raw))

        metadata = dict(existing.metadata) if existing else {}
        metadata.update(
            {
                "dataset_id": dataset["dataset_id"],
                "dataset_version": dataset.get("dataset_version"),
                "fixture_dataset_marker": dataset.get("marker"),
                "verified_display_name": row.get("verified_display_name"),
                "display_name_en": row.get("display_name_en"),
                "national_id_hash": nid_hash,
                "national_id_masked": mask_national_id(national_id),
                "profile_incomplete": bool(defaults.get("profile_incomplete", True)),
                "unverified_fields": [
                    key
                    for key in (
                        "employment_type",
                        "salary_type",
                        "contract_start_date",
                        "email",
                        "hourly_rate",
                        "monthly_salary",
                        "department",
                    )
                    if row.get(key) is None
                ],
            }
        )

        employee = Employee(
            id=employee_id,
            organization_id=org_id,
            employee_number=str(row["employee_number"]).strip(),
            first_name=str(row["first_name"]).strip(),
            last_name=str(row["last_name"]).strip(),
            department_id=department_id,
            employment_type=EmploymentType(employment_raw),
            salary_type=SalaryType(salary_raw),
            contract_start_date=contract_start,
            status=EmployeeStatus.ACTIVE,
            hourly_rate=None,
            monthly_salary=None,
            contract_end_date=None,
            metadata=metadata,
        )
        encrypted = encrypt_national_id(national_id, encryption_key=self._encryption_key)
        if isinstance(self._employees, SqlAlchemyEmployeeRepository):
            await self._employees.save_with_national_id(
                employee, national_id_encrypted=encrypted
            )
        else:
            await self._employees.save(employee)

        await self._audit.append(
            AuditLogEntry(
                action="employee.seed_upserted" if not created else "employee.created",
                resource_type="employee",
                resource_id=employee.id,
                organization_id=org_id,
                details={
                    "dataset_id": DATASET_ID,
                    "employee_number": employee.employee_number,
                    "created": created,
                },
            )
        )
        return employee, created

    async def _upsert_payslip(
        self,
        *,
        employee: Employee,
        slip: dict[str, Any],
        dataset: dict[str, Any],
        checksum: str,
        size: int,
        fixture_path: str,
        mime_type: str,
    ) -> Document:
        document_key = str(slip["document_key"])
        document_id = deterministic_document_id(document_key)
        year = int(slip["payroll_year"])
        month = int(slip["payroll_month"])
        page = int(slip["source_page"])
        filename = Path(fixture_path).name

        metadata = {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset.get("dataset_version"),
            "fixture_dataset_marker": dataset.get("marker"),
            "document_key": document_key,
            "source_document_key": slip["source_document_key"],
            "fixture_path": fixture_path,
            "source_page": page,
            "fixture_classification": slip["fixture_classification"],
            "document_type_key": "payslip",
            "gross_salary": slip.get("gross_salary"),
            "net_salary": slip.get("net_salary"),
            "base_salary": slip.get("base_salary"),
            "regular_hours": slip.get("regular_hours"),
            "overtime_hours": slip.get("overtime_hours"),
            "travel_reimbursement": slip.get("travel_reimbursement"),
            "income_tax": slip.get("income_tax"),
            "national_insurance": slip.get("national_insurance"),
            "health_insurance": slip.get("health_insurance"),
            "pension_deductions": slip.get("pension_deductions"),
            "png_duplicate_excluded": True,
        }

        document = Document(
            id=document_id,
            document_type=DocumentType.PAYSLIP,
            storage_key=(
                f"seed/{DATASET_ID}/{slip['source_document_key']}"
                f"#page={page}"
            ),
            original_filename=f"{Path(filename).stem}_p{page:02d}{Path(filename).suffix}",
            mime_type=mime_type,
            file_size_bytes=size,
            checksum_sha256=checksum,
            status=DocumentStatus.PROCESSED,
            organization_id=employee.organization_id,
            uploaded_by=None,
            employee_id=employee.id,
            period=PayPeriod(year=year, month=month),
            metadata=metadata,
        )
        saved = await self._documents.save(document)
        await self._audit.append(
            AuditLogEntry(
                action="document.seed_upserted",
                resource_type="document",
                resource_id=saved.id,
                organization_id=employee.organization_id,
                details={
                    "dataset_id": DATASET_ID,
                    "document_key": document_key,
                    "employee_number": employee.employee_number,
                    "period_year": year,
                    "period_month": month,
                    "source_page": page,
                    "fixture_classification": slip["fixture_classification"],
                },
            )
        )
        return saved
