"""In-memory integration-style tests for vacation ingest/idempotency/matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from payroll_copilot.application.ports.email import EmailMessage, EmailSendResult, EmailService
from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRecord,
    AuditLogRepository,
    EmployeeListFilter,
    EmployeeRepository,
)
from payroll_copilot.application.ports.vacation_requests import (
    VacationListFilter,
    VacationRequestRepository,
)
from payroll_copilot.application.ports.vacation_settings import (
    EmailOwnershipOtp,
    EmailOwnershipOtpRepository,
    VacationMailboxSettings,
    VacationPipelineAnalyticsRepository,
    VacationSettingsRepository,
)
from payroll_copilot.application.use_cases.manage_vacations import (
    InboundVacationCommand,
    ManageVacationsUseCase,
    ReconcileEmployeeLeaveStatusUseCase,
)
from payroll_copilot.domain.entities import Employee, VacationRequest
from payroll_copilot.domain.enums import (
    EmployeeStatus,
    EmploymentType,
    LeaveStatusSource,
    SalaryType,
    VacationAttentionCode,
    VacationReviewStatus,
)


class FakeEmail(EmailService):
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> EmailSendResult:
        self.sent.append(message)
        return EmailSendResult(message_id="test", provider="console")


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
        return next(
            (
                e
                for e in self.employees
                if e.organization_id == organization_id and e.employee_number == employee_number
            ),
            None,
        )

    async def get_by_national_id_hash(self, organization_id: UUID, national_id_hash: str):
        return None

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        return [e for e in self.employees if e.organization_id == filters.organization_id]

    async def save(self, employee: Employee) -> Employee:
        self.employees = [e for e in self.employees if e.id != employee.id] + [employee]
        return employee


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

    async def delete(self, organization_id: UUID, vacation_id: UUID) -> None:
        self.items.pop(vacation_id, None)

    async def count_unseen(self, organization_id: UUID) -> int:
        return sum(
            1
            for v in self.items.values()
            if v.organization_id == organization_id
            and v.seen_at is None
            and v.review_status
            in {
                VacationReviewStatus.PENDING_APPROVAL.value,
                VacationReviewStatus.REQUIRES_ATTENTION.value,
            }
        )

    async def mark_seen(self, organization_id, *, vacation_ids=None, seen_before=None, seen_at):
        count = 0
        id_set = {str(i) for i in vacation_ids} if vacation_ids else None
        for vac in list(self.items.values()):
            if vac.organization_id != organization_id:
                continue
            if id_set is not None and str(vac.id) not in id_set:
                continue
            if seen_before is not None and vac.created_at and vac.created_at > seen_before:
                continue
            if vac.seen_at is None:
                vac.seen_at = seen_at
                count += 1
        return count


class FakeSettings(VacationSettingsRepository):
    def __init__(self, org: UUID) -> None:
        self.settings = VacationMailboxSettings(organization_id=org)

    async def get(self, organization_id: UUID) -> VacationMailboxSettings:
        return self.settings

    async def save(self, settings: VacationMailboxSettings) -> VacationMailboxSettings:
        self.settings = settings
        return settings


class FakeOtp(EmailOwnershipOtpRepository):
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], EmailOwnershipOtp] = {}

    async def save(self, otp: EmailOwnershipOtp) -> None:
        self.items[(otp.purpose, otp.email)] = otp

    async def get(self, organization_id, *, purpose, email):
        return self.items.get((purpose, email.strip().lower()))

    async def delete(self, organization_id, *, purpose, email) -> None:
        self.items.pop((purpose, email.strip().lower()), None)


class FakePipeline(VacationPipelineAnalyticsRepository):
    def __init__(self) -> None:
        self.events: set[str] = set()
        self.counters: dict[str, dict[str, int]] = {}

    async def increment(self, organization_id, *, day, event_type, amount=1) -> None:
        day_map = self.counters.setdefault(day, {})
        day_map[event_type] = day_map.get(event_type, 0) + amount

    async def try_claim_event(self, organization_id, *, event_id, ttl_epoch) -> bool:
        if event_id in self.events:
            return False
        self.events.add(event_id)
        return True

    async def get_counters(self, organization_id, *, year):
        return {k: v for k, v in self.counters.items() if k.startswith(f"{year}-")}


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


@pytest.fixture
def org_id() -> UUID:
    return uuid4()


@pytest.fixture
def uc(org_id: UUID):
    emp = _employee(org_id, "ada@example.com")
    return ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([emp]),
        audit=FakeAudit(),
        email=FakeEmail(),
    ), emp


@pytest.mark.asyncio
async def test_ingest_idempotent_provider_message(uc, org_id: UUID) -> None:
    manage, _ = uc
    cmd = InboundVacationCommand(
        provider="gmail",
        provider_message_id="msg-1",
        provider_thread_id=None,
        from_email="ada@example.com",
        to_email="hr@co.il",
        subject="Vacation",
        body_text="I need vacation",
        received_at=datetime.now(UTC),
        classification="VACATION",
        intent="new",
        employee_email="ada@example.com",
        employee_name="Ada",
        start_date="2026-08-01",
        end_date="2026-08-10",
        confidence=0.9,
        explanation="clear",
        n8n_attention_codes=[],
    )
    first = await manage.ingest_inbound(org_id, cmd)
    second = await manage.ingest_inbound(org_id, cmd)
    assert first["outcome"] in {"SUCCESS", "REQUIRES_ATTENTION"}
    assert first["durable"] is True
    assert second["outcome"] == "DUPLICATE"
    assert second["vacation_request_id"] == first["vacation_request_id"]


@pytest.mark.asyncio
async def test_ingest_employee_not_found(org_id: UUID) -> None:
    manage = ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([]),
        audit=FakeAudit(),
        email=FakeEmail(),
    )
    result = await manage.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="gmail",
            provider_message_id="msg-2",
            provider_thread_id=None,
            from_email="unknown@example.com",
            to_email=None,
            subject="Vac",
            body_text="body",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="unknown@example.com",
            employee_name=None,
            start_date="2026-08-01",
            end_date="2026-08-05",
            confidence=0.95,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    assert result["durable"] is True
    assert result["outcome"] == "REQUIRES_ATTENTION"
    assert VacationAttentionCode.EMPLOYEE_NOT_FOUND.value in result["attention_codes"]
    vac_id = UUID(result["vacation_request_id"])
    with pytest.raises(ValueError, match="blocked"):
        await manage.approve(org_id, vac_id, actor_user_id=None, confirm_warnings=True)


@pytest.mark.asyncio
async def test_event_dedupe(uc, org_id: UUID) -> None:
    manage, _ = uc
    first = await manage.record_pipeline_event(
        org_id, event_id="evt-1", event_type="EMAIL_OBSERVED"
    )
    second = await manage.record_pipeline_event(
        org_id, event_id="evt-1", event_type="EMAIL_OBSERVED"
    )
    assert first["status"] == "recorded"
    assert second["status"] == "duplicate"


@pytest.mark.asyncio
async def test_health_sets_active_monitored_mailbox(uc, org_id: UUID) -> None:
    manage, _ = uc
    settings = await manage.get_settings(org_id)
    settings.active_monitored_email = "old@example.com"
    await manage._settings.save(settings)
    updated = await manage.apply_mailbox_health(
        org_id,
        monitored_email="new@example.com",
        status="ok",
        checked_at=datetime.now(UTC),
        last_processed_at=None,
        last_processed_message_id=None,
        error_code=None,
        error_message=None,
    )
    assert updated.active_monitored_email == "new@example.com"


@pytest.mark.asyncio
async def test_status_reconciler_preserves_manual_on_leave(org_id: UUID) -> None:
    emp = _employee(org_id, "ada@example.com")
    emp.status = EmployeeStatus.ON_LEAVE
    emp.metadata["leave_status_source"] = LeaveStatusSource.MANUAL.value
    employees = FakeEmployees([emp])
    vacations = FakeVacations()
    reconciler = ReconcileEmployeeLeaveStatusUseCase(
        vacations=vacations,
        employees=employees,
        audit=FakeAudit(),
    )
    await reconciler.execute(org_id)
    assert employees.employees[0].status == EmployeeStatus.ON_LEAVE


@pytest.mark.asyncio
async def test_approve_overlap_requires_confirmation(uc, org_id: UUID) -> None:
    manage, emp = uc
    existing = VacationRequest(
        id=uuid4(),
        organization_id=org_id,
        employee_id=emp.id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
        review_status=VacationReviewStatus.APPROVED.value,
        intent="new",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await manage._vacations.save(existing)
    result = await manage.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="gmail",
            provider_message_id="msg-overlap",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="Overlap",
            body_text="body",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-08-05",
            end_date="2026-08-12",
            confidence=0.95,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    vac_id = UUID(result["vacation_request_id"])
    assert VacationAttentionCode.OVERLAP.value in result["attention_codes"]
    with pytest.raises(ValueError, match="confirmation_required"):
        await manage.approve(org_id, vac_id, actor_user_id=None, confirm_warnings=False)
    approved = await manage.approve(org_id, vac_id, actor_user_id=None, confirm_warnings=True)
    assert approved.review_status == VacationReviewStatus.APPROVED.value


@pytest.mark.asyncio
async def test_bulk_approve_skips_blocked_and_reports_failures(uc, org_id: UUID) -> None:
    manage, emp = uc
    ready = await manage.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="gmail",
            provider_message_id="msg-ready",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="Ready",
            body_text="body",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-09-01",
            end_date="2026-09-03",
            confidence=0.95,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    blocked = await manage.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="gmail",
            provider_message_id="msg-blocked",
            provider_thread_id=None,
            from_email="ghost@example.com",
            to_email=None,
            subject="Blocked",
            body_text="body",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ghost@example.com",
            employee_name=None,
            start_date="2026-09-10",
            end_date="2026-09-12",
            confidence=0.95,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    # Force blocked employee unlink for second (already EMPLOYEE_NOT_FOUND)
    preview = await manage.bulk_approve(
        org_id,
        [UUID(ready["vacation_request_id"]), UUID(blocked["vacation_request_id"])],
        actor_user_id=None,
        confirm_warnings=True,
    )
    assert len(preview["approved"]) == 1
    assert len(preview["skipped_blocked"]) == 1
    assert preview["status"] in {"completed", "partial"} or preview["approved"]


@pytest.mark.asyncio
async def test_otp_invalid_and_expiry(uc, org_id: UUID) -> None:
    manage, _ = uc
    await manage.start_email_verification(
        org_id, purpose="notification", email="notify@example.com", actor_user_id=None
    )
    code = manage._email.sent[-1].text_body.split(":")[1].split()[0]
    with pytest.raises(ValueError, match="otp_invalid"):
        await manage.confirm_email_verification(
            org_id,
            purpose="notification",
            email="notify@example.com",
            code="000000",
            actor_user_id=None,
        )
    otp = await manage._otp.get(org_id, purpose="notification", email="notify@example.com")
    assert otp is not None
    otp.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await manage._otp.save(otp)
    with pytest.raises(ValueError, match="otp_expired"):
        await manage.confirm_email_verification(
            org_id,
            purpose="notification",
            email="notify@example.com",
            code=code,
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_monitored_otp_is_retired(uc, org_id: UUID) -> None:
    manage, _ = uc
    with pytest.raises(ValueError, match="monitored_otp_retired"):
        await manage.start_email_verification(
            org_id, purpose="monitored", email="new@example.com", actor_user_id=None
        )


@pytest.mark.asyncio
async def test_patch_preferences_sets_notification_email_without_otp(uc, org_id: UUID) -> None:
    manage, _ = uc
    saved = await manage.patch_preferences(
        org_id,
        actor_user_id=None,
        notify_on_new_vacation=False,
        notify_on_error_or_attention=True,
        notification_email="  HR@Example.COM ",
        update_notification_email=True,
    )
    assert saved.notification_email_verified == "hr@example.com"
    assert saved.notification_email_pending is None
    assert saved.notify_on_new_vacation is False
    assert saved.notify_on_error_or_attention is True

    cleared = await manage.patch_preferences(
        org_id,
        actor_user_id=None,
        notification_email="",
        update_notification_email=True,
    )
    assert cleared.notification_email_verified is None

    with pytest.raises(ValueError, match="invalid_email"):
        await manage.patch_preferences(
            org_id,
            actor_user_id=None,
            notification_email="not-an-email",
            update_notification_email=True,
        )


@pytest.mark.asyncio
async def test_cancel_proposal_links_related(uc, org_id: UUID) -> None:
    manage, emp = uc
    original = VacationRequest(
        id=uuid4(),
        organization_id=org_id,
        employee_id=emp.id,
        extracted_employee_email="ada@example.com",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 5),
        review_status=VacationReviewStatus.APPROVED.value,
        intent="new",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await manage._vacations.save(original)
    result = await manage.ingest_inbound(
        org_id,
        InboundVacationCommand(
            provider="gmail",
            provider_message_id="msg-cancel",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="Cancel",
            body_text="cancel my vacation",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="cancel",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-10-01",
            end_date="2026-10-05",
            confidence=0.9,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    assert result["outcome"] == "REQUIRES_ATTENTION"
    vac = await manage.get_vacation(org_id, UUID(result["vacation_request_id"]))
    assert vac is not None
    assert vac.related_vacation_id == original.id
    approved = await manage.approve(
        org_id, vac.id, actor_user_id=None, confirm_warnings=True
    )
    assert approved.review_status == VacationReviewStatus.APPROVED.value
    target = await manage.get_vacation(org_id, original.id)
    assert target is not None
    assert target.review_status == VacationReviewStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_mark_seen_respects_cutoff(uc, org_id: UUID) -> None:
    manage, emp = uc
    loaded_at = datetime.now(UTC)
    older = VacationRequest(
        id=uuid4(),
        organization_id=org_id,
        employee_id=emp.id,
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        intent="new",
        created_at=loaded_at - timedelta(minutes=1),
        updated_at=loaded_at - timedelta(minutes=1),
    )
    newer = VacationRequest(
        id=uuid4(),
        organization_id=org_id,
        employee_id=emp.id,
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        start_date=date(2026, 11, 3),
        end_date=date(2026, 11, 4),
        intent="new",
        created_at=loaded_at + timedelta(minutes=1),
        updated_at=loaded_at + timedelta(minutes=1),
    )
    await manage._vacations.save(older)
    await manage._vacations.save(newer)
    updated = await manage.mark_seen(
        org_id,
        vacation_ids=[older.id, newer.id],
        seen_before=loaded_at,
    )
    assert updated == 1
    assert (await manage.get_vacation(org_id, older.id)).seen_at is not None
    assert (await manage.get_vacation(org_id, newer.id)).seen_at is None


@pytest.mark.asyncio
async def test_notification_prefs_and_mandatory_not_stored(uc, org_id: UUID) -> None:
    from payroll_copilot.application.services.vacation_rules import (
        build_notification_instructions,
    )

    manage, _ = uc
    settings = await manage.get_settings(org_id)
    settings.notify_on_new_vacation = False
    settings.notify_on_error_or_attention = False
    settings.notification_email_verified = "hr@example.com"
    quiet = build_notification_instructions(
        settings=settings,
        outcome="SUCCESS",
        durable=True,
        attention_codes=[],
        summary="ok",
    )
    assert quiet["should_send"] is False
    mandatory = build_notification_instructions(
        settings=settings,
        outcome="FAILED",
        durable=False,
        attention_codes=[],
        summary="not stored",
    )
    assert mandatory["should_send"] is True
    assert mandatory["mandatory"] is True
