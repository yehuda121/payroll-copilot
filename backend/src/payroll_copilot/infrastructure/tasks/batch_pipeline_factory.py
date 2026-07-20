"""Infrastructure composition for the reusable batch payslip pipeline.

Single composition entry used by:
- Celery ``BatchPayslipProcessor`` (async bulk jobs)
- Batch review/edit routes that need the same pipeline synchronously

Do not duplicate OCR/parser/validation wiring elsewhere.
"""

from payroll_copilot.application.services.batch_payslip_pipeline import (
    BatchPayslipPipelineService,
)
from payroll_copilot.application.services.parser_layout_context import (
    parser_layout_config_from_settings,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
)
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextUseCase,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.validation import RunValidationUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.infrastructure.ai.payslip_parser_factory import (
    create_payslip_parser,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.ocr.factory import create_ocr_provider
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_organization_bootstrap,
    get_validation_finding_repository,
    get_validation_run_repository,
)
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader
from payroll_copilot.infrastructure.storage.factory import create_object_storage


def create_batch_payslip_pipeline() -> BatchPayslipPipelineService:
    """Compose employee-grade extraction and validation for a Celery worker."""
    settings = get_settings()
    documents = get_document_repository()
    extractions = get_document_extraction_repository()
    employees = get_employee_repository()
    organization_bootstrap = get_organization_bootstrap()

    ocr = ExtractDocumentTextUseCase(
        create_ocr_provider(settings.ocr_provider, settings),
        timeout_seconds=settings.ocr_timeout_seconds,
    )
    parser = ParsePayslipFromOcrUseCase(
        create_payslip_parser(settings),
        timeout_seconds=settings.payslip_parser_timeout_seconds,
        total_budget_seconds=settings.payslip_parser_total_budget_seconds,
        layout_config=parser_layout_config_from_settings(settings),
        evidence_bound_enabled=bool(
            getattr(settings, "payslip_parser_evidence_bound_enabled", False)
        ),
    )
    extract = ExtractGuestPayslipUseCase(
        document_repository=documents,
        extraction_repository=extractions,
        object_storage=create_object_storage(settings),
        organization_bootstrap=organization_bootstrap,
        ocr_use_case=ocr,
        parse_use_case=parser,
    )

    persisted_validation = RunPersistedValidationUseCase(
        run_validation=RunValidationUseCase(
            YamlLegalRulesLoader(settings.legal_rules_path)
        ),
        guest_context_builder=GuestExtractionValidationContextBuilder(extractions),
        document_repository=documents,
        validation_run_repository=get_validation_run_repository(),
        validation_finding_repository=get_validation_finding_repository(),
        organization_bootstrap=organization_bootstrap,
    )
    return BatchPayslipPipelineService(
        extract=extract,
        documents=documents,
        extractions=extractions,
        employees=employees,
        validation=persisted_validation,
    )
