"""FastAPI dependency injection factories."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.use_cases.documents import GetDocumentUseCase, UploadDocumentUseCase
from payroll_copilot.application.use_cases.persisted_validation import (
    GetValidationRunUseCase,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.validation import RunValidationUseCase
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DemoValidationContextBuilder,
)
from payroll_copilot.infrastructure.config.service_resolver import get_resolved_s3_endpoint
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage
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


def get_demo_validation_context_builder() -> DemoValidationContextBuilder:
    return DemoValidationContextBuilder()


def get_run_persisted_validation_use_case(
    run_validation: RunValidationUseCase = Depends(get_run_validation_use_case),
    demo_context_builder: DemoValidationContextBuilder = Depends(get_demo_validation_context_builder),
    document_repository: DocumentRepository = Depends(get_document_repository),
    validation_run_repository: ValidationRunRepository = Depends(get_validation_run_repository),
    validation_finding_repository: ValidationFindingRepository = Depends(
        get_validation_finding_repository
    ),
    organization_bootstrap: OrganizationBootstrapPort = Depends(get_organization_bootstrap),
) -> RunPersistedValidationUseCase:
    return RunPersistedValidationUseCase(
        run_validation=run_validation,
        demo_context_builder=demo_context_builder,
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
