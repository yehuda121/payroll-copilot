"""Tests for admin company employee-data reset."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from payroll_copilot.application.ports.employee_audit import AuditLogEntry, EmployeeListFilter
from payroll_copilot.application.services.org_scoped_redis_cleanup import (
    clear_batch_progress_for_organization,
    clear_manual_review_for_organization,
    clear_organization_redis,
)
from payroll_copilot.application.use_cases.reset_company_employee_data import (
    CONFIRMATION_PHRASE,
    ResetCompanyEmployeeDataUseCase,
    ResetConfirmationError,
    ResetNotEnabledError,
    ResetOrganizationAmbiguousError,
)
from payroll_copilot.domain.entities import Document, Employee, SickLeaveRequest, VacationRequest
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    UserRole,
)
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import UserRecord


ORG_ID = UUID("00000000-0000-4000-8000-000000000001")
ADMIN_ID = uuid4()
ACCOUNTANT_ID = uuid4()
EMPLOYEE_USER_ID = uuid4()
EMP_ID = uuid4()
DOC_ID = uuid4()
RUN_ID = uuid4()


@dataclass
class FakeOrgs:
    ids: list[UUID] = field(default_factory=lambda: [ORG_ID])

    async def list_organization_ids(self) -> list[UUID]:
        return list(self.ids)


@dataclass
class FakeEmployees:
    items: dict[UUID, Employee] = field(default_factory=dict)
    list_calls: list[EmployeeListFilter] = field(default_factory=list)

    async def get_by_id(self, employee_id: UUID) -> Employee | None:
        return self.items.get(employee_id)

    async def get_by_number(self, organization_id: UUID, employee_number: str) -> Employee | None:
        return None

    async def get_by_national_id_hash(self, organization_id: UUID, national_id_hash: str):
        return None

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        self.list_calls.append(filters)
        rows = sorted(
            [e for e in self.items.values() if e.organization_id == filters.organization_id],
            key=lambda e: str(e.id),
        )
        return rows[filters.offset : filters.offset + filters.limit]

    async def save(self, employee: Employee) -> Employee:
        self.items[employee.id] = employee
        return employee

    async def delete_by_ids(self, employee_ids: list[UUID]) -> int:
        n = 0
        for eid in employee_ids:
            if self.items.pop(eid, None) is not None:
                n += 1
        return n


@dataclass
class FakeUsers:
    items: list[UserRecord] = field(default_factory=list)

    async def list_for_organization(self, organization_id: UUID) -> list[UserRecord]:
        return [u for u in self.items if u.organization_id == organization_id]

    async def delete(self, user: UserRecord) -> bool:
        before = len(self.items)
        self.items = [u for u in self.items if u.id != user.id]
        return len(self.items) < before


@dataclass
class FakeDocs:
    by_employee: dict[UUID, list[Document]] = field(default_factory=dict)
    items: dict[UUID, Document] = field(default_factory=dict)

    async def list_for_employee(self, *, organization_id: UUID, employee_id: UUID) -> list[Document]:
        return list(self.by_employee.get(employee_id, []))

    async def delete_by_ids(self, document_ids: list[UUID]) -> int:
        n = 0
        for did in document_ids:
            if self.items.pop(did, None) is not None:
                n += 1
            for emp_id, docs in list(self.by_employee.items()):
                self.by_employee[emp_id] = [d for d in docs if d.id not in document_ids]
        return n if n else len(document_ids)


@dataclass
class FakeExtractions:
    async def delete_for_document_ids(self, document_ids: list[UUID]) -> int:
        return len(document_ids)


@dataclass
class FakeValRuns:
    by_doc: dict[UUID, list[Any]] = field(default_factory=dict)

    async def list_for_document(self, document_id: UUID) -> list[Any]:
        return list(self.by_doc.get(document_id, []))

    async def delete_for_document_ids(self, document_ids: list[UUID]) -> int:
        n = 0
        for did in document_ids:
            runs = self.by_doc.pop(did, [])
            n += len(runs)
        return n


@dataclass
class FakeFindings:
    async def delete_for_run_ids(self, run_ids: list[UUID]) -> int:
        return len(run_ids)


@dataclass
class FakeVacations:
    items: list[VacationRequest] = field(default_factory=list)

    async def list(self, filters) -> list[VacationRequest]:
        rows = [v for v in self.items if v.organization_id == filters.organization_id]
        return rows[filters.offset : filters.offset + filters.limit]

    async def delete(self, organization_id: UUID, vacation_id: UUID) -> None:
        self.items = [v for v in self.items if not (v.organization_id == organization_id and v.id == vacation_id)]


@dataclass
class FakeSickLeaves:
    items: list[SickLeaveRequest] = field(default_factory=list)

    async def list(self, filters) -> list[SickLeaveRequest]:
        rows = [v for v in self.items if v.organization_id == filters.organization_id]
        return rows[filters.offset : filters.offset + filters.limit]

    async def delete(self, organization_id: UUID, sick_leave_id: UUID) -> None:
        self.items = [
            v for v in self.items if not (v.organization_id == organization_id and v.id == sick_leave_id)
        ]


@dataclass
class FakeAudit:
    entries: list[AuditLogEntry] = field(default_factory=list)

    async def append(self, entry: AuditLogEntry):
        self.entries.append(entry)
        return entry

    async def list_recent(self, *, organization_id=None, limit=100, offset=0):
        return []


@dataclass
class FakeStorage:
    objects: dict[str, bytes] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def list_keys(self, prefix: str) -> list[str]:
        return [k for k in self.objects if k.startswith(prefix)]

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list_keys(prefix)
        for key in keys:
            await self.delete(key)
        return len(keys)


@dataclass
class FakeTable:
    items: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        return self.items.get((key["PK"], key["SK"]))

    async def query_eq_pk(self, pk: str, *, sk_begins_with: str | None = None, **kwargs):
        out = []
        for (item_pk, sk), item in self.items.items():
            if item_pk != pk:
                continue
            if sk_begins_with and not sk.startswith(sk_begins_with):
                continue
            out.append(item)
        return out

    async def batch_delete(self, keys_to_delete: list[dict[str, Any]]) -> int:
        n = 0
        for key in keys_to_delete:
            if self.items.pop((key["PK"], key["SK"]), None) is not None:
                n += 1
        return n


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.zsets: dict[str, list[str]] = {}

    def get(self, name: str):
        return self.kv.get(name)

    def delete(self, *names: str):
        for name in names:
            self.kv.pop(name, None)
            self.zsets.pop(name, None)

    def zrevrange(self, name: str, start: int, end: int):
        members = self.zsets.get(name, [])
        if end == -1:
            return list(reversed(members))
        sliced = members[::-1]
        return sliced[start : end + 1]

    def zrem(self, name: str, *values: str):
        members = self.zsets.get(name, [])
        self.zsets[name] = [m for m in members if m not in values]

    def set(self, name: str, value: str):
        self.kv[name] = value

    def zadd(self, name: str, mapping: dict[str, float]):
        members = self.zsets.setdefault(name, [])
        for key in mapping:
            if key not in members:
                members.append(key)


def _employee(emp_id: UUID | None = None) -> Employee:
    return Employee(
        id=emp_id or EMP_ID,
        organization_id=ORG_ID,
        employee_number="E-1",
        first_name="Ada",
        last_name="Lovelace",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )


def _document(emp_id: UUID, storage_key: str) -> Document:
    return Document(
        id=DOC_ID,
        document_type=DocumentType.PAYSLIP,
        storage_key=storage_key,
        original_filename="payslip.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        checksum_sha256="abc",
        status=DocumentStatus.UPLOADED,
        organization_id=ORG_ID,
        employee_id=emp_id,
        created_at=datetime.now(UTC),
    )


def _build_use_case(**overrides) -> tuple[ResetCompanyEmployeeDataUseCase, dict[str, Any]]:
    employees = FakeEmployees()
    users = FakeUsers(
        items=[
            UserRecord(
                id=ADMIN_ID,
                email="admin@example.com",
                role=UserRole.ADMIN,
                organization_id=ORG_ID,
            ),
            UserRecord(
                id=ACCOUNTANT_ID,
                email="acct@example.com",
                role=UserRole.ACCOUNTANT,
                organization_id=ORG_ID,
            ),
            UserRecord(
                id=EMPLOYEE_USER_ID,
                email="emp@example.com",
                role=UserRole.EMPLOYEE,
                organization_id=ORG_ID,
                employee_id=EMP_ID,
            ),
        ]
    )
    docs = FakeDocs()
    storage = FakeStorage()
    table = FakeTable(
        items={
            (f"ORG#{ORG_ID}", "META"): {
                "PK": f"ORG#{ORG_ID}",
                "SK": "META",
                "entity_type": "organization",
                "id": str(ORG_ID),
            },
            (f"ORG#{ORG_ID}", "DEPT#keep"): {
                "PK": f"ORG#{ORG_ID}",
                "SK": "DEPT#keep",
                "entity_type": "department",
            },
            (f"ORG#{ORG_ID}", "VAC_SETTINGS"): {
                "PK": f"ORG#{ORG_ID}",
                "SK": "VAC_SETTINGS",
                "entity_type": "vacation_settings",
            },
            ("LEGAL#SYSTEM", "VECTORHEALTH"): {
                "PK": "LEGAL#SYSTEM",
                "SK": "VECTORHEALTH",
                "entity_type": "legal_vector_health",
            },
            ("POPULAR#GLOBAL", "Q#abc"): {
                "PK": "POPULAR#GLOBAL",
                "SK": "Q#abc",
                "entity_type": "popular_question",
            },
            (f"ORG#{ORG_ID}", "LEAVE_IDEMP#vacation#deadbeef"): {
                "PK": f"ORG#{ORG_ID}",
                "SK": "LEAVE_IDEMP#vacation#deadbeef",
                "entity_type": "leave_idempotency",
            },
        }
    )
    audit = FakeAudit()
    redis = FakeRedis()
    deps = {
        "organizations": FakeOrgs(),
        "employees": employees,
        "users": users,
        "documents": docs,
        "extractions": FakeExtractions(),
        "validation_runs": FakeValRuns(),
        "validation_findings": FakeFindings(),
        "vacations": FakeVacations(),
        "sick_leaves": FakeSickLeaves(),
        "audit": audit,
        "storage": storage,
        "dynamo_table": table,
        "redis": redis,
        "enabled": True,
    }
    deps.update(overrides)
    return ResetCompanyEmployeeDataUseCase(**deps), deps


@pytest.mark.asyncio
async def test_feature_flag_disabled():
    uc, _ = _build_use_case(enabled=False)
    with pytest.raises(ResetNotEnabledError):
        await uc.execute(
            actor_user_id=ADMIN_ID,
            confirmation_phrase=CONFIRMATION_PHRASE,
            confirm_destruction=True,
        )


@pytest.mark.asyncio
async def test_confirmation_phrase_required():
    uc, _ = _build_use_case()
    with pytest.raises(ResetConfirmationError):
        await uc.execute(
            actor_user_id=ADMIN_ID,
            confirmation_phrase="WRONG",
            confirm_destruction=True,
        )


@pytest.mark.asyncio
async def test_second_confirmation_required():
    uc, _ = _build_use_case()
    with pytest.raises(ResetConfirmationError):
        await uc.execute(
            actor_user_id=ADMIN_ID,
            confirmation_phrase=CONFIRMATION_PHRASE,
            confirm_destruction=False,
        )


@pytest.mark.asyncio
async def test_abort_when_not_exactly_one_organization():
    uc, _ = _build_use_case(organizations=FakeOrgs(ids=[ORG_ID, uuid4()]))
    with pytest.raises(ResetOrganizationAmbiguousError):
        await uc.execute(
            actor_user_id=ADMIN_ID,
            confirmation_phrase=CONFIRMATION_PHRASE,
            confirm_destruction=True,
        )


@pytest.mark.asyncio
async def test_reset_deletes_employees_preserves_admin_company_and_config():
    uc, deps = _build_use_case()
    emp = _employee()
    deps["employees"].items[emp.id] = emp
    storage_key = f"organizations/{ORG_ID}/employees/{emp.id}/documents/payslip/{DOC_ID}/payslip.pdf"
    doc = _document(emp.id, storage_key)
    deps["documents"].items[doc.id] = doc
    deps["documents"].by_employee[emp.id] = [doc]
    deps["storage"].objects[storage_key] = b"pdf"
    orphan = f"organizations/{ORG_ID}/employees/{emp.id}/documents/orphan.bin"
    deps["storage"].objects[orphan] = b"x"
    vac = VacationRequest(
        id=uuid4(),
        organization_id=ORG_ID,
        employee_id=emp.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        original_body_s3_key=f"vacations/{ORG_ID}/gmail/msg.txt",
    )
    deps["vacations"].items.append(vac)
    deps["storage"].objects[vac.original_body_s3_key] = b"body"
    deps["validation_runs"].by_doc[doc.id] = [type("R", (), {"id": RUN_ID})()]

    # Redis org-scoped keys
    import json

    redis: FakeRedis = deps["redis"]
    redis.zadd(f"payroll:manual_review:index:{ORG_ID}", {"mr1": 1.0})
    redis.set(
        "payroll:manual_review:mr1",
        json.dumps({"id": "mr1", "organization_id": str(ORG_ID)}),
    )
    redis.zadd("payroll:batch_progress:index", {"bj1": 1.0})
    redis.set(
        "payroll:batch_progress:bj1",
        json.dumps({"batch_job_id": "bj1", "organization_id": str(ORG_ID)}),
    )
    # Other org must survive
    other = str(uuid4())
    redis.zadd("payroll:batch_progress:index", {"bj-other": 2.0})
    redis.set(
        "payroll:batch_progress:bj-other",
        json.dumps({"batch_job_id": "bj-other", "organization_id": other}),
    )

    result = await uc.execute(
        actor_user_id=ADMIN_ID,
        confirmation_phrase=CONFIRMATION_PHRASE,
        confirm_destruction=True,
    )

    assert result.organization_id == ORG_ID
    assert result.counts.employees == 1
    assert result.counts.documents == 1
    assert result.counts.employee_user_bindings == 1
    assert result.counts.vacations == 1
    assert result.counts.leave_idempotency == 1
    assert result.counts.s3_objects >= 2
    assert result.counts.redis_manual_review_items == 1
    assert result.counts.redis_batch_progress_jobs == 1
    assert not deps["employees"].items
    assert deps["documents"].by_employee.get(emp.id, []) == []

    # Admin + accountant preserved
    remaining_users = {u.id: u for u in deps["users"].items}
    assert ADMIN_ID in remaining_users
    assert ACCOUNTANT_ID in remaining_users
    assert EMPLOYEE_USER_ID not in remaining_users

    # Company + config preserved
    table: FakeTable = deps["dynamo_table"]
    assert table.items[(f"ORG#{ORG_ID}", "META")]["entity_type"] == "organization"
    assert (f"ORG#{ORG_ID}", "DEPT#keep") in table.items
    assert (f"ORG#{ORG_ID}", "VAC_SETTINGS") in table.items
    assert ("LEGAL#SYSTEM", "VECTORHEALTH") in table.items
    assert ("POPULAR#GLOBAL", "Q#abc") in table.items
    assert (f"ORG#{ORG_ID}", "LEAVE_IDEMP#vacation#deadbeef") not in table.items

    # Other org batch job preserved
    assert redis.get("payroll:batch_progress:bj-other") is not None
    assert redis.get("payroll:batch_progress:bj1") is None

    # Audit counts only
    assert len(deps["audit"].entries) == 1
    details = deps["audit"].entries[0].details or {}
    assert "counts" in details
    assert "password" not in str(details).lower()
    assert b"pdf" not in str(details).encode()


@pytest.mark.asyncio
async def test_idempotent_second_run():
    uc, deps = _build_use_case()
    first = await uc.execute(
        actor_user_id=ADMIN_ID,
        confirmation_phrase=CONFIRMATION_PHRASE,
        confirm_destruction=True,
    )
    second = await uc.execute(
        actor_user_id=ADMIN_ID,
        confirmation_phrase=CONFIRMATION_PHRASE,
        confirm_destruction=True,
    )
    assert first.counts.employees == 0
    assert second.idempotent is True
    assert second.counts.employees == 0
    assert len(deps["audit"].entries) == 2


@pytest.mark.asyncio
async def test_employee_list_pagination():
    uc, deps = _build_use_case()
    # Force page size behavior by inserting more than one page via monkeypatch constant.
    import payroll_copilot.application.use_cases.reset_company_employee_data as mod

    original = mod._EMPLOYEE_PAGE_SIZE
    mod._EMPLOYEE_PAGE_SIZE = 2
    try:
        for i in range(5):
            emp = _employee(uuid4())
            emp.employee_number = f"E-{i}"
            deps["employees"].items[emp.id] = emp
        result = await uc.execute(
            actor_user_id=ADMIN_ID,
            confirmation_phrase=CONFIRMATION_PHRASE,
            confirm_destruction=True,
        )
        assert result.counts.employees == 5
        # Multiple list pages were requested
        assert len(deps["employees"].list_calls) >= 3
        offsets = [c.offset for c in deps["employees"].list_calls]
        assert 0 in offsets and 2 in offsets and 4 in offsets
    finally:
        mod._EMPLOYEE_PAGE_SIZE = original


@pytest.mark.asyncio
async def test_s3_orphan_prefix_cleanup():
    uc, deps = _build_use_case()
    emp = _employee()
    deps["employees"].items[emp.id] = emp
    orphan = f"organizations/{ORG_ID}/employees/{emp.id}/payroll/2026/01/payslip/x/y.pdf"
    other_org = f"organizations/{uuid4()}/employees/{uuid4()}/documents/a.pdf"
    deps["storage"].objects[orphan] = b"1"
    deps["storage"].objects[other_org] = b"2"
    await uc.execute(
        actor_user_id=ADMIN_ID,
        confirmation_phrase=CONFIRMATION_PHRASE,
        confirm_destruction=True,
    )
    assert orphan not in deps["storage"].objects
    assert other_org in deps["storage"].objects


def test_redis_cleanup_does_not_flush_all():
    redis = FakeRedis()
    redis.set("unrelated:key", "keep")
    redis.zadd(f"payroll:manual_review:index:{ORG_ID}", {"a": 1})
    redis.set(
        "payroll:manual_review:a",
        '{"id":"a","organization_id":"%s"}' % ORG_ID,
    )
    counts = clear_organization_redis(redis, str(ORG_ID))
    assert counts.manual_review_items == 1
    assert redis.get("unrelated:key") == "keep"


def test_redis_batch_filters_by_organization():
    redis = FakeRedis()
    redis.zadd("payroll:batch_progress:index", {"mine": 1, "theirs": 2})
    redis.set(
        "payroll:batch_progress:mine",
        '{"batch_job_id":"mine","organization_id":"%s"}' % ORG_ID,
    )
    redis.set(
        "payroll:batch_progress:theirs",
        '{"batch_job_id":"theirs","organization_id":"%s"}' % uuid4(),
    )
    deleted = clear_batch_progress_for_organization(redis, str(ORG_ID))
    assert deleted == 1
    assert redis.get("payroll:batch_progress:theirs") is not None
    assert clear_manual_review_for_organization(redis, str(ORG_ID)) == 0


@pytest.mark.asyncio
async def test_route_authorization_and_flag(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from payroll_copilot.presentation.api.routes import admin_employee_reset as route_mod
    from payroll_copilot.presentation.api.security import AuthPrincipal

    app = FastAPI()
    app.include_router(route_mod.router, prefix="/admin")

    async def fake_admin():
        return AuthPrincipal(
            user_id=ADMIN_ID,
            email="admin@example.com",
            role=UserRole.ADMIN.value,
            organization_id=ORG_ID,
            employee_id=None,
        )

    async def fake_employee():
        return AuthPrincipal(
            user_id=EMPLOYEE_USER_ID,
            email="emp@example.com",
            role=UserRole.EMPLOYEE.value,
            organization_id=ORG_ID,
            employee_id=EMP_ID,
        )

    class _Settings:
        admin_employee_reset_enabled = False

    settings = _Settings()
    monkeypatch.setattr(route_mod, "get_settings", lambda: settings)

    # Override the exact dependency callable wired into the route (before any patch).
    original_admin_dep = route_mod.require_developer_admin
    app.dependency_overrides[original_admin_dep] = fake_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/admin/reset-employee-data",
            json={
                "confirmation_phrase": CONFIRMATION_PHRASE,
                "confirm_destruction": True,
            },
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "admin_employee_reset_disabled"

    # Non-admin rejected by dependency
    from fastapi import HTTPException

    async def deny_non_admin():
        raise HTTPException(status_code=403, detail={"code": "admin_role_required"})

    app.dependency_overrides[original_admin_dep] = deny_non_admin
    settings.admin_employee_reset_enabled = True
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/admin/reset-employee-data",
            json={
                "confirmation_phrase": CONFIRMATION_PHRASE,
                "confirm_destruction": True,
            },
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_route_confirmation_errors_when_enabled(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from payroll_copilot.presentation.api.routes import admin_employee_reset as route_mod
    from payroll_copilot.presentation.api.security import AuthPrincipal

    app = FastAPI()
    app.include_router(route_mod.router, prefix="/admin")

    async def fake_admin():
        return AuthPrincipal(
            user_id=ADMIN_ID,
            email="admin@example.com",
            role=UserRole.ADMIN.value,
            organization_id=ORG_ID,
            employee_id=None,
        )

    class _Settings:
        admin_employee_reset_enabled = True

    uc, _ = _build_use_case(enabled=True)
    monkeypatch.setattr(route_mod, "get_settings", lambda: _Settings())
    monkeypatch.setattr(route_mod, "get_reset_company_employee_data_use_case", lambda: uc)
    app.dependency_overrides[route_mod.require_developer_admin] = fake_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post(
            "/admin/reset-employee-data",
            json={"confirmation_phrase": "NOPE", "confirm_destruction": True},
        )
        assert bad.status_code == 400
        assert bad.json()["detail"]["code"] == "reset_confirmation_required"

        ok = await client.post(
            "/admin/reset-employee-data",
            json={
                "confirmation_phrase": CONFIRMATION_PHRASE,
                "confirm_destruction": True,
            },
        )
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["organization_id"] == str(ORG_ID)
        assert "counts" in payload
