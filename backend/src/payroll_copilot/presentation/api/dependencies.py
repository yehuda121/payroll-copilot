"""FastAPI dependency injection factories."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from payroll_copilot.application.ports.employee_audit import EmployeeRepository
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.organization_directory import OrganizationDirectoryPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.ports.ocr import OCRProvider
from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.application.services.analytics_service import AnalyticsService
from payroll_copilot.application.use_cases.analytics_admin_census import GetAdminOrgCensusUseCase
from payroll_copilot.application.use_cases.analytics_employee_salary import (
    GetEmployeeSalaryAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_org_payroll import GetOrgPayrollAnalyticsUseCase
from payroll_copilot.application.use_cases.documents import GetDocumentUseCase, UploadDocumentUseCase
from payroll_copilot.application.use_cases.employee_document_workspace import (
    EmployeeDocumentWorkspaceUseCase,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import ExtractGuestPayslipUseCase
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.application.use_cases.parse_payslip import ParsePayslipFromOcrUseCase
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    GetValidationRunUseCase,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.validation import RunValidationUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.infrastructure.ai.payslip_parser_factory import create_payslip_parser
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.ocr.factory import create_ocr_provider
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.infrastructure.storage.factory import create_object_storage
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage
from payroll_copilot.infrastructure.email.factory import create_email_service
from payroll_copilot.application.ports.email import EmailService
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


def get_document_repository() -> DocumentRepository:
    return dynamo_persistence.get_document_repository()


def get_document_extraction_repository() -> DocumentExtractionRepository:
    return dynamo_persistence.get_document_extraction_repository()


def get_validation_run_repository() -> ValidationRunRepository:
    return dynamo_persistence.get_validation_run_repository()


def get_validation_finding_repository() -> ValidationFindingRepository:
    return dynamo_persistence.get_validation_finding_repository()


def get_employee_repository() -> EmployeeRepository:
    return dynamo_persistence.get_employee_repository()


def get_organization_directory() -> OrganizationDirectoryPort:
    return dynamo_persistence.get_organization_directory()


def get_organization_bootstrap() -> OrganizationBootstrapPort:
    return dynamo_persistence.get_organization_bootstrap()


def get_analytics_service(
    documents: DocumentRepository = Depends(get_document_repository),
    extractions: DocumentExtractionRepository = Depends(get_document_extraction_repository),
    validation_runs: ValidationRunRepository = Depends(get_validation_run_repository),
    validation_findings: ValidationFindingRepository = Depends(
        get_validation_finding_repository
    ),
    employees: EmployeeRepository = Depends(get_employee_repository),
    organizations: OrganizationDirectoryPort = Depends(get_organization_directory),
) -> AnalyticsService:
    users = dynamo_persistence.get_user_store()
    employee_salary = GetEmployeeSalaryAnalyticsUseCase(
        documents=documents,
        extractions=extractions,
    )
    org_payroll = GetOrgPayrollAnalyticsUseCase(
        employees=employees,
        documents=documents,
        extractions=extractions,
        validation_runs=validation_runs,
        validation_findings=validation_findings,
    )
    admin_census = GetAdminOrgCensusUseCase(
        employees=employees,
        users=users,
        organizations=organizations,
    )
    return AnalyticsService(
        employee_salary=employee_salary,
        org_payroll=org_payroll,
        admin_census=admin_census,
    )


@lru_cache
def get_object_storage() -> S3ObjectStorage:
    return create_object_storage(get_settings())


@lru_cache
def get_email_service() -> EmailService:
    return create_email_service(get_settings())


@lru_cache
def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    return create_ocr_provider(settings.ocr_provider, settings)


@lru_cache
def get_payslip_parser() -> PayslipParser:
    settings = get_settings()
    return create_payslip_parser(settings)


def get_extract_document_text_use_case(
    ocr_provider: OCRProvider = Depends(get_ocr_provider),
) -> ExtractDocumentTextUseCase:
    settings = get_settings()
    return ExtractDocumentTextUseCase(
        ocr_provider,
        timeout_seconds=settings.ocr_timeout_seconds,
    )


def get_parse_payslip_use_case(
    parser: PayslipParser = Depends(get_payslip_parser),
) -> ParsePayslipFromOcrUseCase:
    settings = get_settings()
    from payroll_copilot.application.services.parser_layout_context import (
        parser_layout_config_from_settings,
    )

    return ParsePayslipFromOcrUseCase(
        parser,
        timeout_seconds=settings.payslip_parser_timeout_seconds,
        total_budget_seconds=settings.payslip_parser_total_budget_seconds,
        layout_config=parser_layout_config_from_settings(settings),
        evidence_bound_enabled=bool(
            getattr(settings, "payslip_parser_evidence_bound_enabled", False)
        ),
    )


def get_extract_guest_payslip_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    extraction_repository: DocumentExtractionRepository = Depends(
        get_document_extraction_repository
    ),
    object_storage: S3ObjectStorage = Depends(get_object_storage),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
    ocr_use_case: ExtractDocumentTextUseCase = Depends(get_extract_document_text_use_case),
) -> ExtractGuestPayslipUseCase:
    return ExtractGuestPayslipUseCase(
        document_repository=document_repository,
        extraction_repository=extraction_repository,
        object_storage=object_storage,
        organization_bootstrap=organization_bootstrap,
        ocr_use_case=ocr_use_case,
    )


def get_upload_document_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    object_storage: S3ObjectStorage = Depends(get_object_storage),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
) -> UploadDocumentUseCase:
    from payroll_copilot.infrastructure.config.org_resolution import (
        SettingsOrganizationIdResolver,
    )

    return UploadDocumentUseCase(
        document_repository=document_repository,
        object_storage=object_storage,
        organization_bootstrap=organization_bootstrap,
        organization_id_resolver=SettingsOrganizationIdResolver(),
    )


def get_employee_document_workspace_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    extraction_repository: DocumentExtractionRepository = Depends(
        get_document_extraction_repository
    ),
    object_storage: S3ObjectStorage = Depends(get_object_storage),
    upload_use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case),
    ocr_use_case: ExtractDocumentTextUseCase = Depends(get_extract_document_text_use_case),
) -> EmployeeDocumentWorkspaceUseCase:
    return EmployeeDocumentWorkspaceUseCase(
        documents=document_repository,
        extractions=extraction_repository,
        storage=object_storage,
        upload_document=upload_use_case,
        ocr=ocr_use_case,
    )


def get_get_document_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> GetDocumentUseCase:
    return GetDocumentUseCase(document_repository=document_repository)


def get_run_validation_use_case() -> RunValidationUseCase:
    settings = get_settings()
    loader = YamlLegalRulesLoader(settings.legal_rules_path)
    return RunValidationUseCase(loader)


def get_guest_extraction_validation_context_builder(
    extraction_repository: DocumentExtractionRepository = Depends(
        get_document_extraction_repository
    ),
) -> GuestExtractionValidationContextBuilder:
    return GuestExtractionValidationContextBuilder(extraction_repository)


def get_correct_guest_extraction_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    extraction_repository: DocumentExtractionRepository = Depends(
        get_document_extraction_repository
    ),
) -> CorrectGuestExtractionUseCase:
    return CorrectGuestExtractionUseCase(
        document_repository=document_repository,
        extraction_repository=extraction_repository,
    )


def get_run_persisted_validation_use_case(
    run_validation: RunValidationUseCase = Depends(get_run_validation_use_case),
    guest_context_builder: GuestExtractionValidationContextBuilder = Depends(
        get_guest_extraction_validation_context_builder
    ),
    document_repository: DocumentRepository = Depends(get_document_repository),
    validation_run_repository: ValidationRunRepository = Depends(get_validation_run_repository),
    validation_finding_repository: ValidationFindingRepository = Depends(
        get_validation_finding_repository
    ),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
) -> RunPersistedValidationUseCase:
    return RunPersistedValidationUseCase(
        run_validation=run_validation,
        guest_context_builder=guest_context_builder,
        document_repository=document_repository,
        validation_run_repository=validation_run_repository,
        validation_finding_repository=validation_finding_repository,
        organization_bootstrap=organization_bootstrap,
    )


def get_validation_run_use_case(
    validation_run_repository: ValidationRunRepository = Depends(get_validation_run_repository),
    validation_finding_repository: ValidationFindingRepository = Depends(
        get_validation_finding_repository
    ),
) -> GetValidationRunUseCase:
    return GetValidationRunUseCase(
        validation_run_repository=validation_run_repository,
        validation_finding_repository=validation_finding_repository,
    )
