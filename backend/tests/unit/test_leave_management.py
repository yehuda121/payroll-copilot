"""Leave Management: active bucket, snapshot, revalidate, duplicate, overlap."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from payroll_copilot.application.ports.vacation_requests import VacationListFilter
from payroll_copilot.application.use_cases.manage_vacations import (
    InboundVacationCommand,
    ManageVacationsUseCase,
)
from payroll_copilot.domain.entities import Employee, VacationRequest
from payroll_copilot.domain.enums import (
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    VacationAttentionCode,
    VacationReviewStatus,
    VacationSource,
)
from payroll_copilot.infrastructure.persistence.dynamodb.vacations import (
    _matches_bucket,
)


class FakeVacations:
    def __init__(self) -> None:
        self.items: dict = {}

    async def get_by_id(self, organization_id, vacation_id):
        vac = self.items.get(vacation_id)
        if vac is None or vac.organization_id != organization_id:
            return None
        return vac

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
        today = datetime.now(UTC).date()
        rows = [v for v in self.items.values() if v.organization_id == filters.organization_id]
        if filters.bucket:
            rows = [v for v in rows if _matches_bucket(v, filters.bucket, today)]
        return rows

    async def list_for_employee(self, organization_id, employee_id):
        return [
            v
            for v in self.items.values()
            if v.organization_id == organization_id and v.employee_id == employee_id
        ]

    async def save(self, vacation):
        self.items[vacation.id] = vacation
        return vacation

    async def delete(self, organization_id, vacation_id):
        vac = self.items.get(vacation_id)
        if vac and vac.organization_id == organization_id:
            del self.items[vacation_id]

    async def count_unseen(self, organization_id):
        return 0

    async def mark_seen(self, organization_id, *, vacation_ids=None, seen_before=None):
        return 0


class FakeEmployees:
    def __init__(self, employees: list[Employee]) -> None:
        self._employees = employees

    async def get_by_id(self, employee_id):
        for emp in self._employees:
            if emp.id == employee_id:
                return emp
        return None

    async def get_by_number(self, organization_id, employee_number):
        return None

    async def get_by_national_id_hash(self, organization_id, national_id_hash):
        return None

    async def list(self, filters):
        return [e for e in self._employees if e.organization_id == filters.organization_id]

    async def save(self, employee):
        return employee


class FakeSettings:
    async def get(self, organization_id):
        from payroll_copilot.application.ports.vacation_settings import VacationMailboxSettings

        return VacationMailboxSettings(organization_id=organization_id)

    async def save(self, settings):
        return settings


class FakeOtp:
    async def put(self, otp):
        return otp

    async def get(self, organization_id, purpose):
        return None

    async def delete(self, organization_id, purpose):
        return None


class FakePipeline:
    async def try_claim_event(self, organization_id, *, event_id, ttl_epoch):
        return True

    async def increment(self, organization_id, *, day, event_type, amount=1):
        return None

    async def get_counters(self, organization_id, *, year):
        return {}


class FakeAudit:
    def __init__(self) -> None:
        self.entries = []

    async def append(self, entry):
        self.entries.append(entry)
        return entry

    async def list_recent(self, **kwargs):
        return []


class FakeEmail:
    async def send(self, message):
        return None


def _emp(org_id, email: str) -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=org_id,
        employee_number="E-1",
        first_name="Ada",
        last_name="Lovelace",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        metadata={"email": email},
    )


def _uc(org_id, employees: list[Employee], vacations: FakeVacations | None = None):
    vacs = vacations or FakeVacations()
    return (
        ManageVacationsUseCase(
            vacations=vacs,
            settings_repo=FakeSettings(),
            otp_repo=FakeOtp(),
            pipeline=FakePipeline(),
            employees=FakeEmployees(employees),
            audit=FakeAudit(),
            email=FakeEmail(),
        ),
        vacs,
    )


def test_active_bucket_includes_unresolved_and_future_approved() -> None:
    today = datetime.now(UTC).date()
    org = uuid4()
    pending = VacationRequest(
        id=uuid4(),
        organization_id=org,
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        start_date=today + timedelta(days=10),
        end_date=today + timedelta(days=12),
    )
    attention = VacationRequest(
        id=uuid4(),
        organization_id=org,
        review_status=VacationReviewStatus.REQUIRES_ATTENTION.value,
        start_date=None,
        end_date=None,
        attention_codes=[VacationAttentionCode.MISSING_END_DATE.value],
    )
    future_approved = VacationRequest(
        id=uuid4(),
        organization_id=org,
        review_status=VacationReviewStatus.APPROVED.value,
        start_date=today + timedelta(days=5),
        end_date=today + timedelta(days=8),
    )
    past_approved = VacationRequest(
        id=uuid4(),
        organization_id=org,
        review_status=VacationReviewStatus.APPROVED.value,
        start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=2),
    )
    cancelled = VacationRequest(
        id=uuid4(),
        organization_id=org,
        review_status=VacationReviewStatus.CANCELLED.value,
        start_date=today + timedelta(days=1),
        end_date=today + timedelta(days=2),
    )
    assert _matches_bucket(pending, "active", today)
    assert _matches_bucket(attention, "active", today)
    assert _matches_bucket(future_approved, "active", today)
    assert not _matches_bucket(past_approved, "active", today)
    assert not _matches_bucket(cancelled, "active", today)
    assert not _matches_bucket(pending, "current", today)


@pytest.mark.asyncio
async def test_ingest_preserves_ai_snapshot_and_update_does_not_overwrite() -> None:
    org = uuid4()
    emp = _emp(org, "ada@example.com")
    uc, vacs = _uc(org, [emp])
    result = await uc.ingest_inbound(
        org,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="msg-1",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="Vacation",
            body_text="I need leave",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-11-01",
            end_date="2026-11-05",
            confidence=0.91,
            explanation="extracted from body",
            n8n_attention_codes=[],
        ),
    )
    assert result["outcome"] == "SUCCESS"
    vac = vacs.items[uuid4().__class__(result["vacation_request_id"])]  # type: ignore[misc]
    vac = next(iter(vacs.items.values()))
    assert vac.ai_extraction_original is not None
    assert vac.ai_extraction_original["employee_email"] == "ada@example.com"
    assert vac.ai_extraction_original["start_date"] == "2026-11-01"

    updated = await uc.update_vacation(
        org,
        vac.id,
        actor_user_id=None,
        extracted_employee_email="other@example.com",
        extracted_employee_name="Other",
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 3),
    )
    assert updated.extracted_employee_email == "other@example.com"
    assert updated.ai_extraction_original["employee_email"] == "ada@example.com"
    assert updated.ai_extraction_original["start_date"] == "2026-11-01"


@pytest.mark.asyncio
async def test_update_rematch_clears_employee_not_found() -> None:
    org = uuid4()
    emp = _emp(org, "ada@example.com")
    uc, vacs = _uc(org, [emp])
    vac = VacationRequest(
        id=uuid4(),
        organization_id=org,
        extracted_employee_email="missing@example.com",
        review_status=VacationReviewStatus.REQUIRES_ATTENTION.value,
        attention_codes=[VacationAttentionCode.EMPLOYEE_NOT_FOUND.value],
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 5),
        source=VacationSource.EMAIL.value,
        ai_extraction_original={
            "employee_email": "missing@example.com",
            "employee_name": None,
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
            "confidence": 0.9,
            "explanation": None,
        },
    )
    await vacs.save(vac)
    updated = await uc.update_vacation(
        org,
        vac.id,
        actor_user_id=None,
        extracted_employee_email="ada@example.com",
    )
    assert updated.employee_id == emp.id
    assert VacationAttentionCode.EMPLOYEE_NOT_FOUND.value not in updated.attention_codes
    assert updated.review_status == VacationReviewStatus.PENDING_APPROVAL.value


@pytest.mark.asyncio
async def test_business_duplicate_suppressed_for_pending_and_approved() -> None:
    org = uuid4()
    emp = _emp(org, "ada@example.com")
    uc, vacs = _uc(org, [emp])
    existing = VacationRequest(
        id=uuid4(),
        organization_id=org,
        employee_id=emp.id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 5),
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        provider="imap",
        provider_message_id="other-msg",
    )
    await vacs.save(existing)
    result = await uc.ingest_inbound(
        org,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="msg-dup",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="dup",
            body_text="dup",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-11-01",
            end_date="2026-11-05",
            confidence=0.9,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    assert result["outcome"] == "DUPLICATE"
    assert result["vacation_request_id"] == str(existing.id)
    assert len(vacs.items) == 1


@pytest.mark.asyncio
async def test_cancelled_and_rejected_do_not_block_duplicate() -> None:
    org = uuid4()
    emp = _emp(org, "ada@example.com")
    uc, vacs = _uc(org, [emp])
    for status in (
        VacationReviewStatus.CANCELLED.value,
        VacationReviewStatus.REJECTED.value,
    ):
        await vacs.save(
            VacationRequest(
                id=uuid4(),
                organization_id=org,
                employee_id=emp.id,
                start_date=date(2026, 11, 1),
                end_date=date(2026, 11, 5),
                review_status=status,
                provider="imap",
                provider_message_id=f"old-{status}",
            )
        )
    result = await uc.ingest_inbound(
        org,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="msg-new",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="new",
            body_text="new",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-11-01",
            end_date="2026-11-05",
            confidence=0.9,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    assert result["outcome"] == "SUCCESS"
    assert len(vacs.items) == 3


@pytest.mark.asyncio
async def test_overlap_marks_both_sides_and_cleanup_on_delete() -> None:
    org = uuid4()
    emp = _emp(org, "ada@example.com")
    uc, vacs = _uc(org, [emp])
    first = VacationRequest(
        id=uuid4(),
        organization_id=org,
        employee_id=emp.id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
        review_status=VacationReviewStatus.APPROVED.value,
        provider="imap",
        provider_message_id="msg-a",
    )
    await vacs.save(first)
    result = await uc.ingest_inbound(
        org,
        InboundVacationCommand(
            provider="imap",
            provider_message_id="msg-b",
            provider_thread_id=None,
            from_email="ada@example.com",
            to_email=None,
            subject="overlap",
            body_text="overlap",
            received_at=datetime.now(UTC),
            classification="VACATION",
            intent="new",
            employee_email="ada@example.com",
            employee_name="Ada",
            start_date="2026-08-08",
            end_date="2026-08-15",
            confidence=0.95,
            explanation=None,
            n8n_attention_codes=[],
        ),
    )
    assert result["outcome"] == "SUCCESS"
    second = vacs.items[uuid4().__class__(result["vacation_request_id"])]  # type: ignore[misc]
    second = next(v for v in vacs.items.values() if str(v.id) == result["vacation_request_id"])
    first = vacs.items[first.id]
    assert VacationAttentionCode.OVERLAP.value in second.attention_codes
    assert first.id in second.overlap_with
    assert VacationAttentionCode.OVERLAP.value in first.attention_codes
    assert second.id in first.overlap_with
    # Warning-only → pending, not requires_attention
    assert second.review_status == VacationReviewStatus.PENDING_APPROVAL.value

    await uc.cancel_or_delete(org, second.id, actor_user_id=None)
    first = vacs.items[first.id]
    assert VacationAttentionCode.OVERLAP.value not in (first.attention_codes or [])
    assert first.overlap_with == []


@pytest.mark.asyncio
async def test_org_isolation_update_and_delete() -> None:
    org_a = uuid4()
    org_b = uuid4()
    emp = _emp(org_a, "ada@example.com")
    uc, vacs = _uc(org_a, [emp])
    vac = VacationRequest(
        id=uuid4(),
        organization_id=org_a,
        employee_id=emp.id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 5),
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
    )
    await vacs.save(vac)
    with pytest.raises(ValueError, match="not_found"):
        await uc.update_vacation(
            org_b, vac.id, actor_user_id=None, extracted_employee_name="X"
        )
    with pytest.raises(ValueError, match="not_found"):
        await uc.cancel_or_delete(org_b, vac.id, actor_user_id=None)
