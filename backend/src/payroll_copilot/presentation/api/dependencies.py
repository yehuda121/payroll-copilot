"""FastAPI dependency injection factories."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.ports.ocr import OCRProvider
from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.application.use_cases.documents import GetDocumentUseCase, UploadDocumentUseCase
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
from payroll_copilot.infrastructure.config.service_resolver import get_resolved_s3_endpoint
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.ocr.factory import create_ocr_provider
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage
from payroll_copilot.infrastructure.persistence.repositories.document_extraction_repository import (
    SqlAlchemyDocumentExtractionRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.organization_bootstrap import (
    SqlAlchemyOrganizationBootstrap,
)
from payroll_copilot.infrastructure.persistence.repositories.validation_finding_repository import (
    SqlAlchemyValidationFindingRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.validation_run_repository import (
    SqlAlchemyValidationRunRepository,
)
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


def get_document_repository(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRepository:
    return SqlAlchemyDocumentRepository(session)


def get_document_extraction_repository(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentExtractionRepository:
    return SqlAlchemyDocumentExtractionRepository(session)


def get_validation_run_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ValidationRunRepository:
    return SqlAlchemyValidationRunRepository(session)


def get_validation_finding_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ValidationFindingRepository:
    return SqlAlchemyValidationFindingRepository(session)


def get_organization_bootstrap(
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationBootstrapPort:
    return SqlAlchemyOrganizationBootstrap(session)


def get_object_storage() -> S3ObjectStorage:
    settings = get_settings()
    return S3ObjectStorage(
        endpoint=get_resolved_s3_endpoint(settings),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )


def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    return create_ocr_provider(settings.ocr_provider, settings)


def get_extract_document_text_use_case(
    ocr_provider: OCRProvider = Depends(get_ocr_provider),
) -> ExtractDocumentTextUseCase:
    settings = get_settings()
    return ExtractDocumentTextUseCase(
        ocr_provider,
        timeout_seconds=settings.ocr_timeout_seconds,
    )


def get_payslip_parser() -> PayslipParser:
    settings = get_settings()
    return create_payslip_parser(settings)


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
        layout_config=parser_layout_config_from_settings(settings),
    )


def get_extract_guest_payslip_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    extraction_repository: DocumentExtractionRepository = Depends(
        get_document_extraction_repository
    ),
    object_storage: S3ObjectStorage = Depends(get_object_storage),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
    ocr_use_case: ExtractDocumentTextUseCase = Depends(get_extract_document_text_use_case),
    parse_use_case: ParsePayslipFromOcrUseCase = Depends(get_parse_payslip_use_case),
) -> ExtractGuestPayslipUseCase:
    return ExtractGuestPayslipUseCase(
        document_repository=document_repository,
        extraction_repository=extraction_repository,
        object_storage=object_storage,
        organization_bootstrap=organization_bootstrap,
        ocr_use_case=ocr_use_case,
        parse_use_case=parse_use_case,
    )


def get_upload_document_use_case(
    document_repository: DocumentRepository = Depends(get_document_repository),
    object_storage: S3ObjectStorage = Depends(get_object_storage),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(
        document_repository=document_repository,
        object_storage=object_storage,
        organization_bootstrap=organization_bootstrap,
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
