"""Amazon DynamoDB persistence adapters (single-table design)."""

from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_email_ownership_otp_repository,
    get_employee_repository,
    get_integration_credential_repository,
    get_organization_bootstrap,
    get_organization_directory,
    get_user_store,
    get_vacation_pipeline_analytics_repository,
    get_vacation_request_repository,
    get_vacation_settings_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
    get_workspace_bootstrap,
    reset_persistence_caches,
)

__all__ = [
    "get_audit_log_repository",
    "get_document_extraction_repository",
    "get_document_repository",
    "get_email_ownership_otp_repository",
    "get_employee_repository",
    "get_integration_credential_repository",
    "get_organization_bootstrap",
    "get_organization_directory",
    "get_user_store",
    "get_vacation_pipeline_analytics_repository",
    "get_vacation_request_repository",
    "get_vacation_settings_repository",
    "get_validation_finding_repository",
    "get_validation_run_repository",
    "get_workspace_bootstrap",
    "reset_persistence_caches",
]
