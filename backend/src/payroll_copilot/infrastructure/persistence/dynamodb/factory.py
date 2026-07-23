"""Factory for DynamoDB persistence adapters."""

from __future__ import annotations

from functools import lru_cache

from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.audit import DynamoAuditLogRepository
from payroll_copilot.infrastructure.persistence.dynamodb.bootstrap import (
    DynamoOrganizationBootstrap,
    DynamoOrganizationWorkspaceBootstrap,
)
from payroll_copilot.infrastructure.persistence.dynamodb.client import create_dynamo_table, get_dynamo_table
from payroll_copilot.infrastructure.persistence.dynamodb.documents import DynamoDocumentRepository
from payroll_copilot.infrastructure.persistence.dynamodb.employees import DynamoEmployeeRepository
from payroll_copilot.infrastructure.persistence.dynamodb.extractions import (
    DynamoDocumentExtractionRepository,
)
from payroll_copilot.infrastructure.persistence.dynamodb.organization_directory import (
    DynamoOrganizationDirectory,
)
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import DynamoUserStore
from payroll_copilot.infrastructure.persistence.dynamodb.validation import (
    DynamoValidationFindingRepository,
    DynamoValidationRunRepository,
)


@lru_cache
def get_document_repository() -> DynamoDocumentRepository:
    return DynamoDocumentRepository(get_dynamo_table())


@lru_cache
def get_document_extraction_repository() -> DynamoDocumentExtractionRepository:
    return DynamoDocumentExtractionRepository(get_dynamo_table())


@lru_cache
def get_validation_run_repository() -> DynamoValidationRunRepository:
    return DynamoValidationRunRepository(get_dynamo_table())


@lru_cache
def get_validation_finding_repository() -> DynamoValidationFindingRepository:
    return DynamoValidationFindingRepository(get_dynamo_table())


@lru_cache
def get_employee_repository() -> DynamoEmployeeRepository:
    return DynamoEmployeeRepository(get_dynamo_table())


@lru_cache
def get_audit_log_repository() -> DynamoAuditLogRepository:
    return DynamoAuditLogRepository(get_dynamo_table())


@lru_cache
def get_organization_bootstrap() -> DynamoOrganizationBootstrap:
    return DynamoOrganizationBootstrap(get_dynamo_table())


@lru_cache
def get_workspace_bootstrap() -> DynamoOrganizationWorkspaceBootstrap:
    return DynamoOrganizationWorkspaceBootstrap(get_dynamo_table())


@lru_cache
def get_user_store() -> DynamoUserStore:
    return DynamoUserStore(get_dynamo_table())


@lru_cache
def get_organization_directory() -> DynamoOrganizationDirectory:
    return DynamoOrganizationDirectory(get_dynamo_table())


@lru_cache
def get_popular_question_repository():  # -> DynamoPopularQuestionRepository
    from payroll_copilot.infrastructure.persistence.dynamodb.popular_questions import (
        DynamoPopularQuestionRepository,
    )

    return DynamoPopularQuestionRepository(get_dynamo_table())


def reset_persistence_caches() -> None:
    """Clear cached table/repos (tests)."""
    get_dynamo_table.cache_clear()
    get_document_repository.cache_clear()
    get_document_extraction_repository.cache_clear()
    get_validation_run_repository.cache_clear()
    get_validation_finding_repository.cache_clear()
    get_employee_repository.cache_clear()
    get_audit_log_repository.cache_clear()
    get_organization_bootstrap.cache_clear()
    get_workspace_bootstrap.cache_clear()
    get_user_store.cache_clear()
    get_organization_directory.cache_clear()
    get_popular_question_repository.cache_clear()
    create_dynamo_table  # keep import used
    get_settings.cache_clear()
