"""CLI entrypoints for accountant portal development seed and cleanup.

Usage (Docker):
  docker compose exec api python -m payroll_copilot.scripts.seed_accountant_portal
  docker compose exec api python -m payroll_copilot.scripts.seed_accountant_portal --cleanup
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path

from payroll_copilot.application.use_cases.seed_accountant_portal import (
    SeedAccountantPortalUseCase,
    SeedDatasetError,
    SeedProductionBlockedError,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_workspace_bootstrap,
)


def _repo_root() -> Path:
    # backend/ when running from source tree; /app in Docker image.
    here = Path(__file__).resolve()
    # .../src/payroll_copilot/scripts/seed_accountant_portal.py -> parents[3] == backend or /app
    return here.parents[3]


async def _run(*, cleanup: bool, dataset: Path | None) -> int:
    settings = get_settings()
    use_case = SeedAccountantPortalUseCase(
        employees=get_employee_repository(),
        documents=get_document_repository(),
        audit_logs=get_audit_log_repository(),
        encryption_key=settings.encryption_key,
        app_env=settings.app_env,
        workspace=get_workspace_bootstrap(),
        extractions=get_document_extraction_repository(),
        repo_root=_repo_root(),
    )
    try:
        if cleanup:
            result = await use_case.cleanup()
        else:
            result = await use_case.seed(dataset_path=dataset)
    except SeedProductionBlockedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SeedDatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(dataclasses.asdict(result), indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed accountant portal demo dataset")
    parser.add_argument("--cleanup", action="store_true", help="Remove seeded dataset rows")
    parser.add_argument("--dataset", type=Path, default=None, help="Optional dataset JSON path")
    args = parser.parse_args(argv)
    return asyncio.run(_run(cleanup=args.cleanup, dataset=args.dataset))


if __name__ == "__main__":
    raise SystemExit(main())
