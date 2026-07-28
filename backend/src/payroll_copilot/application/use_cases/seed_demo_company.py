"""Development-only demo company seeder (additive, no file uploads).

Creates missing employees (up to ~10), digital ID/appendix/contract extractions,
Jan→current-month payslips, then runs the production validation pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import (
    EmployeeListFilter,
    EmployeeRepository,
)
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.demo_company_factory import (
    DATASET_ID,
    DEMO_PAYROLL_ACCOUNTANT_USER_ID,
    TARGET_EMPLOYEE_COUNT,
    DemoEmployeeProfile,
    all_demo_profiles,
    build_appendix_structured,
    build_contract_structured,
    build_national_id_structured,
    build_payslip_structured,
    content_fingerprint,
    demo_document_id,
    demo_extraction_id,
    payslip_months_through_today,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_CONFIRMED,
)
from payroll_copilot.application.services.national_id_privacy import (
    hash_national_id,
    mask_national_id,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.seed_accountant_portal import (
    SeedProductionBlockedError,
    assert_seed_environment_allowed,
)
from payroll_copilot.application.use_cases.validate_employee_payslip import (
    ValidateEmployeePayslipUseCase,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
)
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.persistence.dynamodb.bootstrap import (
    DynamoOrganizationWorkspaceBootstrap,
)
from payroll_copilot.infrastructure.security.field_crypto import encrypt_national_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DemoCompanySeedResult:
    dataset_id: str
    organization_id: str
    employees_existing: int
    employees_created: int
    employees_total: int
    identity_docs_created: int
    appendix_docs_created: int
    contract_docs_created: int
    payslips_created: int
    validations_run: int
    validations_failed: int
    months: list[str]


class SeedDemoCompanyUseCase:
    """Additive demo seeder — never deletes or overwrites existing rows."""

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        workspace: DynamoOrganizationWorkspaceBootstrap,
        encryption_key: str,
        app_env: str,
        validation: RunPersistedValidationUseCase,
        employee_validation: ValidateEmployeePayslipUseCase | None = None,
        target_employees: int = TARGET_EMPLOYEE_COUNT,
        payroll_accountant_id: UUID = DEMO_PAYROLL_ACCOUNTANT_USER_ID,
        today: date | None = None,
    ) -> None:
        self._employees = employees
        self._documents = documents
        self._extractions = extractions
        self._workspace = workspace
        self._encryption_key = encryption_key
        self._app_env = app_env
        self._validation = validation
        self._employee_validation = employee_validation
        self._target_employees = max(1, int(target_employees))
        self._payroll_accountant_id = payroll_accountant_id
        self._today = today or date.today()

    async def execute(self, *, dry_run: bool = False) -> DemoCompanySeedResult:
        assert_seed_environment_allowed(self._app_env)
        org_id = DEMO_ORGANIZATION_ID
        await self._workspace.ensure_organization(org_id, name="Demo Organization")
        department_id = await self._workspace.ensure_default_department(org_id)

        existing = await self._employees.list(
            EmployeeListFilter(
                organization_id=org_id,
                include_disabled=True,
                limit=200,
                offset=0,
            )
        )
        employees_existing = len(existing)
        need = max(0, self._target_employees - employees_existing)

        created_employees = 0
        identity_created = 0
        appendix_created = 0
        contract_created = 0
        payslips_created = 0
        validations_run = 0
        validations_failed = 0

        # Create missing demo profiles first (new employees only).
        used_numbers = {e.employee_number for e in existing}
        used_ids = {e.id for e in existing}
        new_profiles: list[DemoEmployeeProfile] = []
        for profile in all_demo_profiles(today=self._today):
            if len(new_profiles) >= need:
                break
            if profile.employee_number in used_numbers:
                continue
            if profile.employee_id in used_ids:
                continue
            if await self._employees.get_by_number(org_id, profile.employee_number) is not None:
                continue
            if await self._employees.get_by_national_id_hash(
                org_id, hash_national_id(profile.national_id)
            ) is not None:
                continue
            new_profiles.append(profile)

        if dry_run:
            months = payslip_months_through_today(today=self._today)
            return DemoCompanySeedResult(
                dataset_id=DATASET_ID,
                organization_id=str(org_id),
                employees_existing=employees_existing,
                employees_created=len(new_profiles),
                employees_total=employees_existing + len(new_profiles),
                identity_docs_created=0,
                appendix_docs_created=0,
                contract_docs_created=0,
                payslips_created=0,
                validations_run=0,
                validations_failed=0,
                months=[f"{y:04d}-{m:02d}" for y, m in months],
            )

        for profile in new_profiles:
            await self._create_employee(
                org_id=org_id,
                department_id=department_id,
                profile=profile,
            )
            created_employees += 1

        # Refresh full employee list after creates.
        all_employees = await self._employees.list(
            EmployeeListFilter(
                organization_id=org_id,
                include_disabled=True,
                limit=200,
                offset=0,
            )
        )

        profile_by_number = {
            p.employee_number: p for p in all_demo_profiles(today=self._today)
        }
        months = payslip_months_through_today(today=self._today)

        for employee in all_employees:
            profile = profile_by_number.get(employee.employee_number)
            # Existing non-demo employees still get payslip gap-fill when possible.
            docs = await self._documents.list_for_employee(
                organization_id=org_id,
                employee_id=employee.id,
            )
            types_present = {doc.document_type for doc in docs}

            if profile is not None:
                if DocumentType.NATIONAL_ID not in types_present:
                    await self._create_fixed_document(
                        employee=employee,
                        profile=profile,
                        document_type=DocumentType.NATIONAL_ID,
                        structured=build_national_id_structured(profile),
                        filename="teudat-zehut.json",
                    )
                    identity_created += 1
                if DocumentType.ID_APPENDIX not in types_present:
                    await self._create_fixed_document(
                        employee=employee,
                        profile=profile,
                        document_type=DocumentType.ID_APPENDIX,
                        structured=build_appendix_structured(profile),
                        filename="id-appendix.json",
                    )
                    appendix_created += 1
                if DocumentType.CONTRACT not in types_present:
                    await self._create_fixed_document(
                        employee=employee,
                        profile=profile,
                        document_type=DocumentType.CONTRACT,
                        structured=build_contract_structured(profile),
                        filename="employment-contract.json",
                    )
                    contract_created += 1

            for year, month in months:
                existing_slip = await self._documents.find_payslip_for_period(
                    organization_id=org_id,
                    employee_id=employee.id,
                    period_year=year,
                    period_month=month,
                )
                if existing_slip is not None:
                    continue

                slip_profile = profile or self._profile_from_employee(employee)
                national_id = await self._resolve_national_id(employee, slip_profile)
                document, _extraction = await self._create_payslip(
                    employee=employee,
                    profile=slip_profile,
                    year=year,
                    month=month,
                    national_id=national_id,
                )
                payslips_created += 1
                try:
                    await self._run_validation(employee=employee, document_id=document.id)
                    validations_run += 1
                except Exception as exc:  # noqa: BLE001 — continue seeding
                    validations_failed += 1
                    logger.warning(
                        "demo seed validation failed employee=%s period=%04d-%02d: %s",
                        employee.employee_number,
                        year,
                        month,
                        exc,
                    )

        return DemoCompanySeedResult(
            dataset_id=DATASET_ID,
            organization_id=str(org_id),
            employees_existing=employees_existing,
            employees_created=created_employees,
            employees_total=len(all_employees),
            identity_docs_created=identity_created,
            appendix_docs_created=appendix_created,
            contract_docs_created=contract_created,
            payslips_created=payslips_created,
            validations_run=validations_run,
            validations_failed=validations_failed,
            months=[f"{y:04d}-{m:02d}" for y, m in months],
        )

    def _profile_from_employee(self, employee: Employee) -> DemoEmployeeProfile:
        salary = employee.monthly_salary or Decimal("10000")
        return DemoEmployeeProfile(
            slot=0,
            national_id="000000000",
            first_name=employee.first_name,
            last_name=employee.last_name,
            employee_number=employee.employee_number,
            monthly_salary=Decimal(str(salary)),
            hire_date=employee.contract_start_date,
            children=(),
            raise_month=6,
            bonus_month=None,
            overtime_months=(3, 7),
        )

    async def _resolve_national_id(
        self,
        employee: Employee,
        profile: DemoEmployeeProfile,
    ) -> str | None:
        if profile.national_id and profile.national_id != "000000000":
            return profile.national_id
        try:
            encrypted = await self._employees.get_national_id_encrypted(employee.id)
        except NotImplementedError:
            encrypted = None
        if not encrypted:
            return None
        from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id

        return decrypt_national_id(encrypted, encryption_key=self._encryption_key)

    async def _create_employee(
        self,
        *,
        org_id: UUID,
        department_id: UUID,
        profile: DemoEmployeeProfile,
    ) -> Employee:
        employee = Employee(
            id=profile.employee_id,
            organization_id=org_id,
            employee_number=profile.employee_number,
            first_name=profile.first_name,
            last_name=profile.last_name,
            department_id=department_id,
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=profile.hire_date,
            status=EmployeeStatus.ACTIVE,
            monthly_salary=profile.monthly_salary,
            payroll_accountant_id=self._payroll_accountant_id,
            metadata={
                "dataset_id": DATASET_ID,
                "national_id_hash": hash_national_id(profile.national_id),
                "national_id_masked": mask_national_id(profile.national_id),
                "verified_display_name": profile.full_name,
                "source": "demo_company_seed",
            },
        )
        encrypted = encrypt_national_id(
            profile.national_id,
            encryption_key=self._encryption_key,
        )
        return await self._employees.save_with_national_id(
            employee,
            national_id_encrypted=encrypted,
        )

    async def _create_fixed_document(
        self,
        *,
        employee: Employee,
        profile: DemoEmployeeProfile,
        document_type: DocumentType,
        structured: dict[str, Any],
        filename: str,
    ) -> None:
        doc_key = (
            f"{DATASET_ID}|{employee.id}|{document_type.value}|v1"
        )
        document_id = demo_document_id(doc_key)
        fingerprint = content_fingerprint(f"{doc_key}:{sorted(structured.keys())}")
        now = datetime.utcnow()
        document = Document(
            id=document_id,
            document_type=document_type,
            storage_key=f"seed/{DATASET_ID}/{employee.id}/{document_type.value}/{filename}",
            original_filename=filename,
            mime_type="application/json",
            file_size_bytes=0,
            checksum_sha256=fingerprint,
            status=DocumentStatus.PROCESSED,
            organization_id=employee.organization_id,
            uploaded_by=self._payroll_accountant_id,
            employee_id=employee.id,
            period=None,
            metadata={
                "dataset_id": DATASET_ID,
                "source": "demo_company_seed",
                "publication_status": "published",
                "logical_only": True,
                "no_physical_file": True,
            },
            created_at=now,
        )
        await self._documents.save(document)
        extraction = DocumentExtraction(
            id=demo_extraction_id(document_id),
            document_id=document_id,
            engine="demo_company_seed",
            raw_text="",
            structured_data=structured,
            overall_confidence=0.96,
            extraction_version=1,
            created_at=now,
            parser_model="demo_company_seed",
            language="he",
            ocr_status="skipped",
            parser_status="completed",
            confirmation_status=CONFIRMATION_CONFIRMED,
            confirmed_at=now,
            confirmed_by=self._payroll_accountant_id,
            updated_at=now,
        )
        await self._extractions.save(extraction)

    async def _create_payslip(
        self,
        *,
        employee: Employee,
        profile: DemoEmployeeProfile,
        year: int,
        month: int,
        national_id: str | None,
    ) -> tuple[Document, DocumentExtraction]:
        period_key = f"{year:04d}-{month:02d}"
        doc_key = f"{DATASET_ID}|{employee.id}|payslip|{period_key}"
        document_id = demo_document_id(doc_key)
        structured = build_payslip_structured(
            profile,
            employee_id=employee.id,
            year=year,
            month=month,
        )
        if national_id:
            structured["employee_id"] = {
                "value": national_id,
                "confidence": 0.97,
                "source_text": national_id,
                "status": "FOUND",
                "edited_by_user": False,
                "original_value": national_id,
            }
            additional = structured.setdefault("additional_fields", {})
            if isinstance(additional, dict):
                additional["national_id"] = {
                    "value": national_id,
                    "confidence": 0.97,
                    "source_text": national_id,
                    "status": "FOUND",
                    "edited_by_user": False,
                    "original_value": national_id,
                }
        fingerprint = content_fingerprint(doc_key)
        now = datetime.utcnow()
        document = Document(
            id=document_id,
            document_type=DocumentType.PAYSLIP,
            storage_key=(
                f"seed/{DATASET_ID}/{employee.id}/payroll/{year:04d}/{month:02d}/"
                f"payslip/{document_id}/payslip.json"
            ),
            original_filename=f"payslip-{period_key}.json",
            mime_type="application/json",
            file_size_bytes=0,
            checksum_sha256=fingerprint,
            status=DocumentStatus.PROCESSED,
            organization_id=employee.organization_id,
            uploaded_by=self._payroll_accountant_id,
            employee_id=employee.id,
            period=PayPeriod(year=year, month=month),
            metadata={
                "dataset_id": DATASET_ID,
                "source": "demo_company_seed",
                "publication_status": "published",
                "logical_only": True,
                "no_physical_file": True,
                "selected_period_year": year,
                "selected_period_month": month,
                "period_resolution": "confirmed",
                "lifecycle_status": "published",
            },
            created_at=now,
        )
        await self._documents.save(document)
        extraction = DocumentExtraction(
            id=demo_extraction_id(document_id),
            document_id=document_id,
            engine="demo_company_seed",
            raw_text="",
            structured_data=structured,
            overall_confidence=0.95,
            extraction_version=1,
            created_at=now,
            parser_model="demo_company_seed",
            language="he",
            ocr_status="skipped",
            parser_status="completed",
            confirmation_status=CONFIRMATION_CONFIRMED,
            confirmed_at=now,
            confirmed_by=self._payroll_accountant_id,
            updated_at=now,
        )
        await self._extractions.save(extraction)
        return document, extraction

    async def _run_validation(self, *, employee: Employee, document_id: UUID) -> None:
        encrypted = None
        try:
            encrypted = await self._employees.get_national_id_encrypted(employee.id)
        except NotImplementedError:
            encrypted = None

        if self._employee_validation is not None and encrypted is not None:
            await self._employee_validation.execute(
                document_id=document_id,
                employee=employee,
                user_id=self._payroll_accountant_id,
                national_id_encrypted=encrypted,
                locale="he",
            )
            return

        from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id

        trusted = None
        if encrypted is not None:
            trusted = decrypt_national_id(
                encrypted,
                encryption_key=self._encryption_key,
            )
        await self._validation.execute(
            RunPersistedValidationCommand(
                document_id=document_id,
                employee_id=employee.id,
                include_historical=True,
                include_contract_rag=True,
                locale="he",
                trusted_national_id=trusted,
                merge_with_previous=False,
            )
        )


__all__ = [
    "DemoCompanySeedResult",
    "SeedDemoCompanyUseCase",
    "SeedProductionBlockedError",
]
