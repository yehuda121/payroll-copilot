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
from payroll_copilot.infrastructure.persistence.database import async_session_factory
from payroll_copilot.infrastructure.persistence.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)


def _repo_root() -> Path:
    # backend/ when running from source tree; /app in Docker image.
    here = Path(__file__).resolve()
    # .../src/payroll_copilot/scripts/seed_accountant_portal.py -> parents[3] == backend or /app
    return here.parents[3]


async def _run(*, cleanup: bool, dataset: Path | None) -> int:
    settings = get_settings()
    async with async_session_factory() as session:
        use_case = SeedAccountantPortalUseCase(
            session=session,
            employees=SqlAlchemyEmployeeRepository(session),
            documents=SqlAlchemyDocumentRepository(session),
            audit_logs=SqlAlchemyAuditLogRepository(session),
            encryption_key=settings.encryption_key,
            app_env=settings.app_env,
            repo_root=_repo_root(),
        )
        try:
            if cleanup:
                result = await use_case.cleanup()
                await session.commit()
                print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))
                return 0
            result = await use_case.execute(dataset)
            await session.commit()
            print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))
            return 0
        except SeedProductionBlockedError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            await session.rollback()
            return 2
        except SeedDatasetError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            await session.rollback()
            return 1
        except Exception:
            await session.rollback()
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent accountant portal development seed / cleanup."
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help=f"Remove only records belonging to the accountant_portal_seed_v1 dataset.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Optional path to accountant_portal_seed.json",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(cleanup=args.cleanup, dataset=args.dataset))


if __name__ == "__main__":
    raise SystemExit(main())
