"""Admin reset: delete all employees and employee-related business data for the sole company.

Preserves: organization META, departments, admin/accountant user bindings, vacation
settings, integrations, LEGAL#SYSTEM, POPULAR#GLOBAL, and global admin configuration.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRepository,
    EmployeeListFilter,
    EmployeeRepository,
)
from payroll_copilot.application.ports.organization_directory import OrganizationDirectoryPort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.ports.sick_leave_requests import (
    SickLeaveListFilter,
    SickLeaveRequestRepository,
)
from payroll_copilot.application.ports.vacation_requests import (
    VacationListFilter,
    VacationRequestRepository,
)
from payroll_copilot.application.services.org_scoped_redis_cleanup import (
    RedisClientProtocol,
    clear_organization_redis,
)
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import UserRecord

logger = logging.getLogger(__name__)

CONFIRMATION_PHRASE = "RESET_EMPLOYEE_DATA"
_EMPLOYEE_PAGE_SIZE = 500
_LEAVE_PAGE_SIZE = 500


class UserStoreProtocol(Protocol):
    async def list_for_organization(self, organization_id: UUID) -> list[UserRecord]: ...

    async def delete(self, user: UserRecord) -> bool: ...


class ObjectStorageResetProtocol(Protocol):
    async def delete(self, key: str) -> None: ...

    async def list_keys(self, prefix: str) -> list[str]: ...

    async def delete_prefix(self, prefix: str) -> int: ...


class DynamoTableProtocol(Protocol):
    async def query_eq_pk(
        self,
        pk: str,
        *,
        sk_begins_with: str | None = None,
        index_name: str | None = None,
        scan_index_forward: bool = True,
        limit: int | None = None,
        filter_expression: Any = None,
    ) -> list[dict[str, Any]]: ...

    async def batch_delete(self, keys: list[dict[str, Any]]) -> int: ...

    async def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None: ...


class ResetCompanyEmployeeDataError(Exception):
    """Base error for admin employee reset."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ResetNotEnabledError(ResetCompanyEmployeeDataError):
    def __init__(self) -> None:
        super().__init__(
            "admin_employee_reset_disabled",
            "Admin employee data reset is disabled.",
        )


class ResetConfirmationError(ResetCompanyEmployeeDataError):
    def __init__(self, message: str = "Confirmation phrase or second confirmation is invalid.") -> None:
        super().__init__("reset_confirmation_required", message)


class ResetOrganizationAmbiguousError(ResetCompanyEmployeeDataError):
    def __init__(self, count: int) -> None:
        super().__init__(
            "organization_count_invalid",
            f"Reset requires exactly one organization; found {count}.",
        )


@dataclass
class ResetDeletionCounts:
    employees: int = 0
    employee_user_bindings: int = 0
    documents: int = 0
    extractions: int = 0
    validation_runs: int = 0
    validation_findings: int = 0
    vacations: int = 0
    sick_leaves: int = 0
    leave_idempotency: int = 0
    s3_objects: int = 0
    s3_orphan_prefix_objects: int = 0
    redis_manual_review_items: int = 0
    redis_batch_progress_jobs: int = 0
    redis_guest_session_keys: int = 0
    organization_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResetCompanyEmployeeDataResult:
    organization_id: UUID
    counts: ResetDeletionCounts = field(default_factory=ResetDeletionCounts)
    idempotent: bool = False


class ResetCompanyEmployeeDataUseCase:
    def __init__(
        self,
        *,
        organizations: OrganizationDirectoryPort,
        employees: EmployeeRepository,
        users: UserStoreProtocol,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository,
        vacations: VacationRequestRepository,
        sick_leaves: SickLeaveRequestRepository,
        audit: AuditLogRepository,
        storage: ObjectStorageResetProtocol,
        dynamo_table: DynamoTableProtocol,
        redis: RedisClientProtocol | None = None,
        enabled: bool = False,
    ) -> None:
        self._organizations = organizations
        self._employees = employees
        self._users = users
        self._documents = documents
        self._extractions = extractions
        self._validation_runs = validation_runs
        self._validation_findings = validation_findings
        self._vacations = vacations
        self._sick_leaves = sick_leaves
        self._audit = audit
        self._storage = storage
        self._table = dynamo_table
        self._redis = redis
        self._enabled = enabled

    async def execute(
        self,
        *,
        actor_user_id: UUID,
        confirmation_phrase: str,
        confirm_destruction: bool,
    ) -> ResetCompanyEmployeeDataResult:
        if not self._enabled:
            raise ResetNotEnabledError()
        if (confirmation_phrase or "").strip() != CONFIRMATION_PHRASE:
            raise ResetConfirmationError(
                f'Confirmation phrase must be exactly "{CONFIRMATION_PHRASE}".'
            )
        if not confirm_destruction:
            raise ResetConfirmationError("Second confirmation (confirm_destruction) is required.")

        org_ids = await self._organizations.list_organization_ids()
        if len(org_ids) != 1:
            raise ResetOrganizationAmbiguousError(len(org_ids))
        organization_id = org_ids[0]

        # Guard: company META must exist and will never be deleted by this use case.
        meta = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": "META"}
        )
        if meta is None or meta.get("entity_type") != "organization":
            raise ResetOrganizationAmbiguousError(0)

        counts = ResetDeletionCounts(organization_id=str(organization_id))
        s3_keys: set[str] = set()

        employees = await self._list_all_employees(organization_id)
        employee_ids = [e.id for e in employees]

        document_ids: list[UUID] = []
        for employee in employees:
            docs = await self._documents.list_for_employee(
                organization_id=organization_id,
                employee_id=employee.id,
            )
            for doc in docs:
                document_ids.append(doc.id)
                if doc.storage_key:
                    s3_keys.add(doc.storage_key)

        # Collect validation run ids before deleting runs (for findings).
        run_ids: list[UUID] = []
        for document_id in document_ids:
            runs = await self._validation_runs.list_for_document(document_id)
            run_ids.extend(run.id for run in runs)

        if run_ids:
            counts.validation_findings = await self._validation_findings.delete_for_run_ids(
                run_ids
            )
        if document_ids:
            counts.validation_runs = await self._validation_runs.delete_for_document_ids(
                document_ids
            )
            # Extractions also best-effort delete artifact S3 keys internally.
            counts.extractions = await self._extractions.delete_for_document_ids(document_ids)
            for document_id in document_ids:
                for key in await self._storage.list_keys(f"documents/{document_id}/"):
                    s3_keys.add(key)
                # Batch bulk uploads use exact key documents/{id} (no trailing slash).
                s3_keys.add(f"documents/{document_id}")

        for key in list(s3_keys):
            try:
                await self._storage.delete(key)
                counts.s3_objects += 1
            except Exception:
                logger.debug("S3 delete skipped/failed for key=%s", key, exc_info=True)

        if document_ids:
            counts.documents = await self._documents.delete_by_ids(document_ids)

        # Leave records (org-scoped) + related body files.
        vacation_s3, vac_count = await self._delete_vacations(organization_id)
        sick_s3, sick_count = await self._delete_sick_leaves(organization_id)
        counts.vacations = vac_count
        counts.sick_leaves = sick_count
        for key in vacation_s3 | sick_s3:
            try:
                await self._storage.delete(key)
                counts.s3_objects += 1
            except Exception:
                logger.debug("S3 leave body delete failed key=%s", key, exc_info=True)

        counts.leave_idempotency = await self._delete_leave_idempotency(organization_id)

        # Employee user bindings only — never admin or accountant without employee_id.
        counts.employee_user_bindings = await self._delete_employee_user_bindings(
            organization_id
        )

        if employee_ids:
            counts.employees = await self._employees.delete_by_ids(employee_ids)

        # Safe orphan prefix cleanup under employee tree only.
        orphan_prefix = f"organizations/{organization_id}/employees/"
        try:
            orphan_deleted = await self._storage.delete_prefix(orphan_prefix)
            counts.s3_orphan_prefix_objects = orphan_deleted
            counts.s3_objects += orphan_deleted
        except Exception:
            logger.warning(
                "Orphan S3 prefix cleanup failed for %s",
                orphan_prefix,
                exc_info=True,
            )

        # Leave body prefixes for this org (employee-related leave files).
        for leave_prefix in (
            f"vacations/{organization_id}/",
            f"sick-leaves/{organization_id}/",
        ):
            try:
                n = await self._storage.delete_prefix(leave_prefix)
                counts.s3_orphan_prefix_objects += n
                counts.s3_objects += n
            except Exception:
                logger.debug("Leave prefix cleanup failed for %s", leave_prefix, exc_info=True)

        redis_counts = clear_organization_redis(
            self._redis,
            str(organization_id),
            guest_document_ids=[],
        )
        counts.redis_manual_review_items = redis_counts.manual_review_items
        counts.redis_batch_progress_jobs = redis_counts.batch_progress_jobs
        counts.redis_guest_session_keys = redis_counts.guest_session_keys

        # Verify company META still present after cleanup.
        meta_after = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": "META"}
        )
        if meta_after is None:
            raise RuntimeError("Organization META was unexpectedly removed during reset.")

        remaining = await self._list_all_employees(organization_id)
        idempotent = (
            counts.employees == 0
            and counts.documents == 0
            and counts.vacations == 0
            and counts.sick_leaves == 0
            and not remaining
        )

        await self._audit.append(
            AuditLogEntry(
                action="admin.reset_employee_data",
                resource_type="organization",
                resource_id=organization_id,
                organization_id=organization_id,
                user_id=actor_user_id,
                details={
                    "counts": counts.to_dict(),
                    "idempotent": idempotent,
                    # Never log document contents or credentials.
                },
            )
        )

        return ResetCompanyEmployeeDataResult(
            organization_id=organization_id,
            counts=counts,
            idempotent=idempotent,
        )

    async def _list_all_employees(self, organization_id: UUID) -> list:
        out: list = []
        offset = 0
        while True:
            page = await self._employees.list(
                EmployeeListFilter(
                    organization_id=organization_id,
                    include_disabled=True,
                    limit=_EMPLOYEE_PAGE_SIZE,
                    offset=offset,
                )
            )
            if not page:
                break
            out.extend(page)
            offset += len(page)
            if len(page) < _EMPLOYEE_PAGE_SIZE:
                break
        return out

    async def _delete_vacations(self, organization_id: UUID) -> tuple[set[str], int]:
        s3_keys: set[str] = set()
        deleted = 0
        while True:
            page = await self._vacations.list(
                VacationListFilter(
                    organization_id=organization_id,
                    limit=_LEAVE_PAGE_SIZE,
                    offset=0,
                )
            )
            if not page:
                break
            for vac in page:
                if vac.original_body_s3_key:
                    s3_keys.add(vac.original_body_s3_key)
                await self._vacations.delete(organization_id, vac.id)
                deleted += 1
            if len(page) < _LEAVE_PAGE_SIZE:
                break
        return s3_keys, deleted

    async def _delete_sick_leaves(self, organization_id: UUID) -> tuple[set[str], int]:
        s3_keys: set[str] = set()
        deleted = 0
        while True:
            page = await self._sick_leaves.list(
                SickLeaveListFilter(
                    organization_id=organization_id,
                    limit=_LEAVE_PAGE_SIZE,
                    offset=0,
                )
            )
            if not page:
                break
            for leave in page:
                if leave.original_body_s3_key:
                    s3_keys.add(leave.original_body_s3_key)
                await self._sick_leaves.delete(organization_id, leave.id)
                deleted += 1
            if len(page) < _LEAVE_PAGE_SIZE:
                break
        return s3_keys, deleted

    async def _delete_leave_idempotency(self, organization_id: UUID) -> int:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="LEAVE_IDEMP#",
        )
        keys_to_delete = [
            {"PK": item["PK"], "SK": item["SK"]}
            for item in items
            if item.get("entity_type") == "leave_idempotency"
        ]
        if not keys_to_delete:
            return 0
        return await self._table.batch_delete(keys_to_delete)

    async def _delete_employee_user_bindings(self, organization_id: UUID) -> int:
        users = await self._users.list_for_organization(organization_id)
        deleted = 0
        for user in users:
            role = user.role.value if hasattr(user.role, "value") else str(user.role)
            if role == UserRole.ADMIN.value:
                continue
            if role == UserRole.ACCOUNTANT.value and user.employee_id is None:
                continue
            # Employee bindings, or accountant/employee hybrids linked to an employee.
            if role == UserRole.EMPLOYEE.value or user.employee_id is not None:
                await self._users.delete(user)
                deleted += 1
        return deleted
