"""CLI for development-only demo company seed.

Usage (Docker):
  docker compose exec api python -m payroll_copilot.scripts.seed_demo_company
  docker compose exec api python -m payroll_copilot.scripts.seed_demo_company --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from payroll_copilot.application.services.confirmed_employment_terms_loader import (
    ConfirmedEmploymentTermsLoader,
)
from payroll_copilot.application.services.demo_company_factory import TARGET_EMPLOYEE_COUNT
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.use_cases.seed_accountant_portal import (
    SeedProductionBlockedError,
)
from payroll_copilot.application.use_cases.seed_demo_company import SeedDemoCompanyUseCase
from payroll_copilot.application.use_cases.validate_employee_payslip import (
    ValidateEmployeePayslipUseCase,
)
from payroll_copilot.application.use_cases.validation import RunValidationUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_organization_bootstrap,
    get_validation_finding_repository,
    get_validation_run_repository,
    get_workspace_bootstrap,
)
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


def _build_use_case(*, target_employees: int) -> SeedDemoCompanyUseCase:
    settings = get_settings()
    documents = get_document_repository()
    extractions = get_document_extraction_repository()
    employees = get_employee_repository()
    organization_bootstrap = get_organization_bootstrap()

    persisted = RunPersistedValidationUseCase(
        run_validation=RunValidationUseCase(
            YamlLegalRulesLoader(settings.legal_rules_path)
        ),
        guest_context_builder=GuestExtractionValidationContextBuilder(extractions),
        document_repository=documents,
        validation_run_repository=get_validation_run_repository(),
        validation_finding_repository=get_validation_finding_repository(),
        organization_bootstrap=organization_bootstrap,
        employee_repository=employees,
        employment_terms_loader=ConfirmedEmploymentTermsLoader(
            documents=documents,
            extractions=extractions,
        ),
    )
    employee_validation = ValidateEmployeePayslipUseCase(
        documents=documents,
        extractions=extractions,
        validation=persisted,
    )
    return SeedDemoCompanyUseCase(
        employees=employees,
        documents=documents,
        extractions=extractions,
        workspace=get_workspace_bootstrap(),
        encryption_key=settings.encryption_key,
        app_env=settings.app_env,
        validation=persisted,
        employee_validation=employee_validation,
        target_employees=target_employees,
    )


async def _run(*, dry_run: bool, target_employees: int) -> int:
    use_case = _build_use_case(target_employees=target_employees)
    try:
        result = await use_case.execute(dry_run=dry_run)
    except SeedProductionBlockedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed a small development demo company (additive, no files)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned creates without writing.",
    )
    parser.add_argument(
        "--target-employees",
        type=int,
        default=TARGET_EMPLOYEE_COUNT,
        help=f"Approximate total employees in the demo org (default {TARGET_EMPLOYEE_COUNT}).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(dry_run=bool(args.dry_run), target_employees=int(args.target_employees))
    )


if __name__ == "__main__":
    raise SystemExit(main())
