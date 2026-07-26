"""Sick leave domain + batch leave ingest tests (in-memory)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRecord,
    AuditLogRepository,
    EmployeeListFilter,
    EmployeeRepository,
)
from payroll_copilot.application.ports.sick_leave_requests import (
    SickLeaveListFilter,
    SickLeaveRequestRepository,
)
from payroll_copilot.application.ports.vacation_requests import (
    VacationListFilter,
    VacationRequestRepository,
)
from payroll_copilot.application.ports.vacation_settings import (
    VacationMailboxSettings,
    VacationSettingsRepository,
)
from payroll_copilot.application.use_cases.ingest_leave_batch import (
    InboundLeaveBatchItem,
    IngestLeaveBatchUseCase,
    build_batch_notification,
)
from payroll_copilot.application.use_cases.manage_sick_leaves import (
    InboundSickLeaveCommand,
    ManageSickLeavesUseCase,
)
from payroll_copilot.application.use_cases.manage_vacations import (
    InboundVacationCommand,
    ManageVacationsUseCase,
)
from payroll_copilot.domain.entities import Employee, SickLeaveRequest, VacationRequest
from payroll_copilot.domain.enums import (
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    SickLeaveAttentionCode,
    SickLeaveReviewStatus,
    VacationReviewStatus,
)


class FakeAudit(AuditLogRepository):
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def append(self, entry: AuditLogEntry) -> AuditLogRecord:
        self.entries.append(entry)
        return AuditLogRecord(
            id=len(self.entries),
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            organization_id=entry.organization_id,
            user_id=entry.user_id,
            details=entry.details or {},
            created_at=datetime.now(UTC),
        )

    async def list_recent(self, *, organization_id=None, limit=100, offset=0):
        return []


class FakeEmployees(EmployeeRepository):
    def __init__(self, employees: list[Employee] | None = None) -> None:
        self.employees = list(employees or [])

    async def get_by_id(self, employee_id: UUID) -> Employee | None:
        return next((e for e in self.employees if e.id == employee_id), None)

    async def get_by_number(self, organization_id: UUID, employee_number: str) -> Employee | None:
        return None

    async def get_by_national_id_hash(self, organization_id: UUID, national_id_hash: str):
        return None

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        return [e for e in self.employees if e.organization_id == filters.organization_id]

    async def save(self, employee: Employee) -> Employee:
        self.employees = [e for e in self.employees if e.id != employee.id] + [employee]
        return employee


class FakeSickLeaves(SickLeaveRequestRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, SickLeaveRequest] = {}

    async def get_by_id(self, organization_id: UUID, sick_leave_id: UUID):
        row = self.items.get(sick_leave_id)
        if row and row.organization_id == organization_id:
            return row
        return None

    async def get_by_provider_message(self, organization_id, *, provider, provider_message_id):
        for row in self.items.values():
            if (
                row.organization_id == organization_id
                and row.provider == provider
                and row.provider_message_id == provider_message_id
            ):
                return row
        return None

    async def list(self, filters: SickLeaveListFilter):
        return [v for v in self.items.values() if v.organization_id == filters.organization_id]

    async def list_for_employee(self, organization_id: UUID, employee_id: UUID):
        return [
            v
            for v in self.items.values()
            if v.organization_id == organization_id and v.employee_id == employee_id
        ]

    async def save(self, sick_leave: SickLeaveRequest) -> SickLeaveRequest:
        self.items[sick_leave.id] = sick_leave
        return sick_leave

    async def create_inbound(
        self, sick_leave: SickLeaveRequest
    ) -> tuple[SickLeaveRequest, bool]:
        if not getattr(self, "_idemp", None):
            self._idemp = {}
        if getattr(self, "_fail_next_inbound", False):
            self._fail_next_inbound = False
            raise RuntimeError("simulated_transaction_failure")
        provider = (sick_leave.provider or "").strip().lower()
        message_id = (sick_leave.provider_message_id or "").strip()
        if provider and message_id:
            key = f"{sick_leave.organization_id}:{provider}:{message_id}"
            existing_id = self._idemp.get(key)
            if existing_id is not None:
                existing = self.items.get(existing_id)
                if existing is not None:
                    return existing, False
            self._idemp[key] = sick_leave.id
        self.items[sick_leave.id] = sick_leave
        return sick_leave, True

    async def delete(self, organization_id: UUID, sick_leave_id: UUID) -> None:
        self.items.pop(sick_leave_id, None)

    async def count_unseen(self, organization_id: UUID) -> int:
        return sum(
            1
            for v in self.items.values()
            if v.organization_id == organization_id
            and v.seen_at is None
            and v.review_status
            in {
                SickLeaveReviewStatus.PENDING_APPROVAL.value,
                SickLeaveReviewStatus.REQUIRES_ATTENTION.value,
            }
        )

    async def mark_seen(self, organization_id, *, sick_leave_ids=None, seen_before=None, seen_at):
        count = 0
        id_set = {str(i) for i in sick_leave_ids} if sick_leave_ids else None
        for row in list(self.items.values()):
            if row.organization_id != organization_id:
                continue
            if id_set is not None and str(row.id) not in id_set:
                continue
            if row.seen_at is None:
                row.seen_at = seen_at
                count += 1
        return count


class FakeVacations(VacationRequestRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, VacationRequest] = {}

    async def get_by_id(self, organization_id: UUID, vacation_id: UUID):
        vac = self.items.get(vacation_id)
        if vac and vac.organization_id == organization_id:
            return vac
        return None

    async def get_by_provider_message(self, organization_id, *, provider, provider_message_id):
        for vac in self.items.values():
            if (
                vac.organization_id == organization_id
                and vac.provider == provider
                and vac.provider_message_id == provider_message_id
            ):
                return vac
        return None

    async def list(self, filters: VacationListFilter):
        return [v for v in self.items.values() if v.organization_id == filters.organization_id]

    async def list_for_employee(self, organization_id: UUID, employee_id: UUID):
        return [
            v
            for v in self.items.values()
            if v.organization_id == organization_id and v.employee_id == employee_id
        ]

    async def save(self, vacation: VacationRequest) -> VacationRequest:
        self.items[vacation.id] = vacation
        return vacation

    async def create_inbound(
        self, vacation: VacationRequest
    ) -> tuple[VacationRequest, bool]:
        if not getattr(self, "_idemp", None):
            self._idemp = {}
        provider = (vacation.provider or "").strip().lower()
        message_id = (vacation.provider_message_id or "").strip()
        if provider and message_id:
            key = f"{vacation.organization_id}:{provider}:{message_id}"
            existing_id = self._idemp.get(key)
            if existing_id is not None:
                existing = self.items.get(existing_id)
                if existing is not None:
                    return existing, False
            self._idemp[key] = vacation.id
        self.items[vacation.id] = vacation
        return vacation, True

    async def delete(self, organization_id: UUID, vacation_id: UUID) -> None:
        self.items.pop(vacation_id, None)

    async def count_unseen(self, organization_id: UUID) -> int:
        return 0

    async def mark_seen(self, organization_id, *, vacation_ids=None, seen_before=None, seen_at):
        return 0


class FakeSettings(VacationSettingsRepository):
    def __init__(self, org: UUID) -> None:
        self.settings = VacationMailboxSettings(
            organization_id=org,
            notification_email_verified="payroll@example.com",
            active_monitored_email="mailbox@example.com",
        )

    async def get(self, organization_id: UUID) -> VacationMailboxSettings:
        return self.settings

    async def save(self, settings: VacationMailboxSettings) -> VacationMailboxSettings:
        self.settings = settings
        return settings


def _employee(org: UUID, email: str) -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=org,
        employee_number="E1",
        first_name="Ada",
        last_name="Lovelace",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
        metadata={"email": email},
    )


def _sick_cmd(**overrides) -> InboundSickLeaveCommand:
    base = dict(
        provider="imap",
        provider_message_id="msg-sick-1",
        provider_thread_id=None,
        from_email="ada@example.com",
        to_email="hr@example.com",
        subject="Sick leave",
        body_text="I am sick",
        received_at=datetime.now(UTC),
        classification="SICK_LEAVE",
        intent="new",
        employee_email="ada@example.com",
        employee_name="Ada Lovelace",
        start_date="2026-08-03",
        end_date="2026-08-04",
        confidence=0.96,
        explanation="clear",
        n8n_attention_codes=[],
    )
    base.update(overrides)
    return InboundSickLeaveCommand(**base)


def _batch_item(*, classification: str, message_id: str, **overrides) -> InboundLeaveBatchItem:
    base = dict(
        provider="imap",
        provider_message_id=message_id,
        provider_thread_id=None,
        from_email="ada@example.com",
        to_email="hr@example.com",
        subject="Leave",
        body_text="body",
        received_at=datetime.now(UTC),
        classification=classification,
        intent="new",
        employee_email="ada@example.com",
        employee_name="Ada Lovelace",
        start_date="2026-08-10",
        end_date="2026-08-12",
        confidence=0.96,
        explanation="ok",
        n8n_attention_codes=[],
    )
    base.update(overrides)
    return InboundLeaveBatchItem(**base)


@pytest.fixture
def org_id() -> UUID:
    return uuid4()


@pytest.fixture
def sick_stack(org_id: UUID):
    emp = _employee(org_id, "ada@example.com")
    employees = FakeEmployees([emp])
    sick = FakeSickLeaves()
    settings = FakeSettings(org_id)
    audit = FakeAudit()
    uc = ManageSickLeavesUseCase(
        sick_leaves=sick,
        settings_repo=settings,
        employees=employees,
        audit=audit,
    )
    return {
        "uc": uc,
        "sick": sick,
        "settings": settings,
        "employees": employees,
        "emp": emp,
        "audit": audit,
    }


def _vacation_uc(org_id: UUID, employees: FakeEmployees, vacations: FakeVacations, settings: FakeSettings, audit: FakeAudit):
    from payroll_copilot.application.ports.email import EmailMessage, EmailSendResult, EmailService
    from payroll_copilot.application.ports.vacation_settings import (
        EmailOwnershipOtpRepository,
        VacationPipelineAnalyticsRepository,
    )

    class FakeEmail(EmailService):
        async def send(self, message: EmailMessage) -> EmailSendResult:
            return EmailSendResult(message_id="t", provider="console")

    class FakeOtp(EmailOwnershipOtpRepository):
        async def save(self, otp): ...
        async def get(self, organization_id, *, purpose, email):
            return None
        async def delete(self, organization_id, *, purpose, email) -> None: ...

    class FakePipeline(VacationPipelineAnalyticsRepository):
        async def increment(self, organization_id, *, day, event_type, amount=1) -> None: ...
        async def try_claim_event(self, organization_id, *, event_id, ttl_epoch) -> bool:
            return True
        async def get_counters(self, organization_id, *, year):
            return {}

    return ManageVacationsUseCase(
        vacations=vacations,
        settings_repo=settings,
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=employees,
        audit=audit,
        email=FakeEmail(),
    )


@pytest.mark.asyncio
async def test_sick_leave_create_and_match(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    result = await uc.ingest_inbound(org_id, _sick_cmd())
    assert result["outcome"] == "SUCCESS"
    assert result["sick_leave_request_id"]
    rows = await uc.list_sick_leaves(org_id)
    assert len(rows) == 1
    assert rows[0].employee_id == sick_stack["emp"].id
    assert rows[0].review_status == SickLeaveReviewStatus.PENDING_APPROVAL.value


@pytest.mark.asyncio
async def test_sick_leave_employee_not_found(org_id: UUID) -> None:
    settings = FakeSettings(org_id)
    uc = ManageSickLeavesUseCase(
        sick_leaves=FakeSickLeaves(),
        settings_repo=settings,
        employees=FakeEmployees([]),
        audit=FakeAudit(),
    )
    result = await uc.ingest_inbound(org_id, _sick_cmd(provider_message_id="nf-1"))
    assert result["outcome"] == "REQUIRES_ATTENTION"
    assert SickLeaveAttentionCode.EMPLOYEE_NOT_FOUND.value in result["attention_codes"]


@pytest.mark.asyncio
async def test_sick_leave_missing_dates(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    result = await uc.ingest_inbound(
        org_id,
        _sick_cmd(provider_message_id="md-1", start_date=None, end_date=None),
    )
    assert result["outcome"] == "REQUIRES_ATTENTION"
    assert SickLeaveAttentionCode.MISSING_START_DATE.value in result["attention_codes"]
    assert SickLeaveAttentionCode.MISSING_END_DATE.value in result["attention_codes"]


@pytest.mark.asyncio
async def test_sick_leave_invalid_dates(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    result = await uc.ingest_inbound(
        org_id,
        _sick_cmd(provider_message_id="id-1", start_date="2026-08-10", end_date="2026-08-01"),
    )
    assert result["outcome"] == "REQUIRES_ATTENTION"
    assert SickLeaveAttentionCode.END_BEFORE_START.value in result["attention_codes"]


@pytest.mark.asyncio
async def test_sick_leave_low_confidence(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    result = await uc.ingest_inbound(
        org_id, _sick_cmd(provider_message_id="lc-1", confidence=0.4)
    )
    assert result["outcome"] == "SUCCESS"
    assert SickLeaveAttentionCode.LOW_CONFIDENCE.value in result["attention_codes"]


@pytest.mark.asyncio
async def test_sick_leave_provider_and_content_duplicates(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    first = await uc.ingest_inbound(org_id, _sick_cmd())
    second = await uc.ingest_inbound(org_id, _sick_cmd())
    assert first["outcome"] == "SUCCESS"
    assert second["outcome"] == "DUPLICATE"
    assert second["summary_code"] == "DUPLICATE_PROVIDER_MESSAGE"

    third = await uc.ingest_inbound(
        org_id,
        _sick_cmd(provider_message_id="msg-sick-2"),
    )
    assert third["outcome"] == "DUPLICATE"
    assert third["summary_code"] == "DUPLICATE_CONTENT"
    assert len(sick_stack["sick"].items) == 1


@pytest.mark.asyncio
async def test_sick_leave_overlap_same_domain_only(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    await uc.ingest_inbound(
        org_id,
        _sick_cmd(
            provider_message_id="ov-1",
            start_date="2026-09-01",
            end_date="2026-09-05",
        ),
    )
    result = await uc.ingest_inbound(
        org_id,
        _sick_cmd(
            provider_message_id="ov-2",
            start_date="2026-09-04",
            end_date="2026-09-08",
        ),
    )
    assert result["outcome"] == "SUCCESS"
    assert SickLeaveAttentionCode.OVERLAP.value in result["attention_codes"]


@pytest.mark.asyncio
async def test_sick_leave_update_cancel_approve_delete(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    created = await uc.ingest_inbound(org_id, _sick_cmd(provider_message_id="base"))
    base_id = UUID(created["sick_leave_request_id"])
    await uc.approve(org_id, base_id, actor_user_id=uuid4(), confirm_warnings=True)

    update = await uc.ingest_inbound(
        org_id,
        _sick_cmd(
            provider_message_id="upd",
            intent="update",
            start_date="2026-08-03",
            end_date="2026-08-06",
            target_hints={"prior_start": "2026-08-03", "prior_end": "2026-08-04"},
        ),
    )
    assert update["outcome"] == "REQUIRES_ATTENTION"
    upd_id = UUID(update["sick_leave_request_id"])
    row = await uc.get_sick_leave(org_id, upd_id)
    assert row is not None
    assert row.related_sick_leave_id == base_id

    cancel = await uc.ingest_inbound(
        org_id,
        _sick_cmd(
            provider_message_id="can",
            intent="cancel",
            start_date="2026-08-03",
            end_date="2026-08-04",
        ),
    )
    assert cancel["outcome"] == "REQUIRES_ATTENTION"

    pending = await uc.create_manual(
        org_id,
        actor_user_id=uuid4(),
        employee_id=sick_stack["emp"].id,
        employee_email="ada@example.com",
        employee_name="Ada",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2),
    )
    deleted = await uc.cancel_or_delete(org_id, pending.id, actor_user_id=uuid4())
    assert deleted is None


@pytest.mark.asyncio
async def test_sick_leave_bulk_and_tenant_isolation(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    a = await uc.ingest_inbound(
        org_id, _sick_cmd(provider_message_id="b1", start_date="2026-11-01", end_date="2026-11-02")
    )
    b = await uc.ingest_inbound(
        org_id, _sick_cmd(provider_message_id="b2", start_date="2026-11-10", end_date="2026-11-11")
    )
    ids = [UUID(a["sick_leave_request_id"]), UUID(b["sick_leave_request_id"])]
    bulk = await uc.bulk_approve(org_id, ids, actor_user_id=uuid4(), confirm_warnings=True)
    assert len(bulk["approved"]) == 2

    other = uuid4()
    assert await uc.get_sick_leave(other, ids[0]) is None
    listed = await uc.list_sick_leaves(other)
    assert listed == []

    deleted = await uc.bulk_delete(org_id, ids, actor_user_id=uuid4())
    assert len(deleted["cancelled"]) == 2


@pytest.mark.asyncio
async def test_batch_mixed_duplicates_and_notification(org_id: UUID) -> None:
    emp = _employee(org_id, "ada@example.com")
    employees = FakeEmployees([emp])
    vacations = FakeVacations()
    sick = FakeSickLeaves()
    settings = FakeSettings(org_id)
    audit = FakeAudit()
    vac_uc = _vacation_uc(org_id, employees, vacations, settings, audit)
    sick_uc = ManageSickLeavesUseCase(
        sick_leaves=sick,
        settings_repo=settings,
        employees=employees,
        audit=audit,
    )
    batch = IngestLeaveBatchUseCase(
        vacations=vac_uc,
        sick_leaves=sick_uc,
        settings_repo=settings,
    )

    # Seed duplicates
    await vac_uc.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="v-dup",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email="hr@example.com",
            subject="v",
            body_text="v",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-08-01",
            end_date="2026-08-05",
            confidence=0.96,
            explanation="ok",
            n8n_attention_codes=[],
        ),
    )
    await sick_uc.ingest_inbound(
        org_id,
        _sick_cmd(
            provider_message_id="s-dup",
            start_date="2026-08-03",
            end_date="2026-08-04",
        ),
    )

    result = await batch.execute(
        org_id,
        [
            _batch_item(
                classification="VACATION",
                message_id="v-dup",
                start_date="2026-08-01",
                end_date="2026-08-05",
            ),
            _batch_item(
                classification="VACATION",
                message_id="v-new",
                start_date="2026-12-01",
                end_date="2026-12-05",
            ),
            _batch_item(
                classification="SICK_LEAVE",
                message_id="s-dup",
                start_date="2026-08-03",
                end_date="2026-08-04",
            ),
            _batch_item(
                classification="SICK_LEAVE",
                message_id="s-attn",
                employee_email="missing@example.com",
                start_date="2026-12-10",
                end_date="2026-12-11",
            ),
            _batch_item(
                classification="VACATION",
                message_id="v-new-2",
                start_date="2026-12-20",
                end_date="2026-12-21",
            ),
            _batch_item(classification="OTHER", message_id="other-1"),
        ],
    )

    assert result["received_count"] == 6
    assert result["duplicate_count"] == 2
    assert result["ignored_count"] == 1
    # Duplicates excluded from results
    assert all(r["outcome"] != "DUPLICATE" for r in result["results"])
    outcomes = {r["outcome"] for r in result["results"]}
    assert "SUCCESS" in outcomes
    assert "REQUIRES_ATTENTION" in outcomes
    assert "IGNORED" in outcomes
    assert result["notification"]["should_send"] is True
    assert result["notification"]["to_email"] == "payroll@example.com"
    assert "Sick Leave" in result["notification"]["body_text"]
    assert "Vacation" in result["notification"]["body_text"]
    assert "already-existing" in result["notification"]["body_text"]


@pytest.mark.asyncio
async def test_batch_all_duplicates_no_notification(org_id: UUID) -> None:
    emp = _employee(org_id, "ada@example.com")
    employees = FakeEmployees([emp])
    vacations = FakeVacations()
    sick = FakeSickLeaves()
    settings = FakeSettings(org_id)
    audit = FakeAudit()
    vac_uc = _vacation_uc(org_id, employees, vacations, settings, audit)
    sick_uc = ManageSickLeavesUseCase(
        sick_leaves=sick,
        settings_repo=settings,
        employees=employees,
        audit=audit,
    )
    await vac_uc.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="only",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email="hr@example.com",
            subject="v",
            body_text="v",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-08-01",
            end_date="2026-08-02",
            confidence=0.96,
            explanation="ok",
            n8n_attention_codes=[],
        ),
    )
    batch = IngestLeaveBatchUseCase(
        vacations=vac_uc,
        sick_leaves=sick_uc,
        settings_repo=settings,
    )
    result = await batch.execute(
        org_id,
        [
            _batch_item(
                classification="VACATION",
                message_id="only",
                start_date="2026-08-01",
                end_date="2026-08-02",
            )
        ],
    )
    assert result["duplicate_count"] == 1
    assert result["results"] == []
    assert result["notification"]["should_send"] is False


def test_batch_notification_pref_and_fallback_recipient() -> None:
    settings = VacationMailboxSettings(
        organization_id=uuid4(),
        notification_email_verified=None,
        active_monitored_email="fallback@example.com",
        notify_on_new_vacation=False,
        notify_on_error_or_attention=True,
        notify_on_new_sick_leave=True,
        notify_on_sick_leave_error_or_attention=False,
    )
    results = [
        {
            "classification": "VACATION",
            "outcome": "SUCCESS",
            "review_status": "pending_approval",
            "employee_name": "A",
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
            "attention_codes": [],
        },
        {
            "classification": "SICK_LEAVE",
            "outcome": "SUCCESS",
            "review_status": "pending_approval",
            "employee_name": "B",
            "start_date": "2026-08-03",
            "end_date": "2026-08-04",
            "attention_codes": [],
        },
    ]
    note = build_batch_notification(
        settings=settings,
        results=results,
        duplicate_count=0,
        received_count=2,
    )
    assert note["should_send"] is True
    assert note["to_email"] == "fallback@example.com"
    assert "Sick Leave" in note["body_text"]
    assert "Vacation" not in note["body_text"]

    settings.notification_email_verified = None
    settings.active_monitored_email = None
    note2 = build_batch_notification(
        settings=settings,
        results=results,
        duplicate_count=0,
        received_count=2,
    )
    assert note2["should_send"] is False


@pytest.mark.asyncio
async def test_create_manual_same_org_employee_succeeds(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    emp = sick_stack["emp"]
    saved = await uc.create_manual(
        org_id,
        actor_user_id=uuid4(),
        employee_id=emp.id,
        employee_email="ada@example.com",
        employee_name="Ada",
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 2),
    )
    assert saved.employee_id == emp.id
    assert saved.organization_id == org_id


@pytest.mark.asyncio
async def test_create_manual_foreign_org_employee_rejected(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    foreign = _employee(uuid4(), "other@example.com")
    sick_stack["employees"].employees.append(foreign)
    with pytest.raises(ValueError, match="employee_not_found"):
        await uc.create_manual(
            org_id,
            actor_user_id=uuid4(),
            employee_id=foreign.id,
            employee_email="other@example.com",
            employee_name="Other",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 2),
        )
    assert list(sick_stack["sick"].items.values()) == []


@pytest.mark.asyncio
async def test_sick_ingest_provider_race_single_record(sick_stack, org_id: UUID) -> None:
    uc: ManageSickLeavesUseCase = sick_stack["uc"]
    cmd = _sick_cmd(provider_message_id="race-sick")
    first = await uc.ingest_inbound(org_id, cmd)
    second = await uc.ingest_inbound(org_id, cmd)
    assert first["outcome"] in {"SUCCESS", "REQUIRES_ATTENTION"}
    assert second["outcome"] == "DUPLICATE"
    assert second["sick_leave_request_id"] == first["sick_leave_request_id"]
    assert len(sick_stack["sick"].items) == 1
