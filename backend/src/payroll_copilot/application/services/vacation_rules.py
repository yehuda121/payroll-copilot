"""Vacation domain helpers — matching, validation, overlap, notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.application.ports.vacation_requests import VacationRequestRepository
from payroll_copilot.application.ports.vacation_settings import VacationMailboxSettings
from payroll_copilot.domain.entities import Employee, VacationRequest
from payroll_copilot.domain.enums import (
    VacationAttentionCode,
    VacationIntent,
    VacationReviewStatus,
)
from payroll_copilot.domain.enums import EmailAutomationStatus


LOW_CONFIDENCE_THRESHOLD = 0.85
MAX_BODY_INLINE_CHARS = 80_000


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def intervals_overlap(
    start_a: date | None,
    end_a: date | None,
    start_b: date | None,
    end_b: date | None,
) -> bool:
    if start_a is None or end_a is None or start_b is None or end_b is None:
        return False
    return start_a <= end_b and end_a >= start_b


@dataclass(frozen=True, slots=True)
class EmployeeMatchResult:
    employee: Employee | None
    code: str | None  # EMPLOYEE_NOT_FOUND | EMPLOYEE_AMBIGUOUS | None


async def match_employee_by_email(
    employees: EmployeeRepository,
    organization_id: UUID,
    email: str | None,
) -> EmployeeMatchResult:
    normalized = normalize_email(email)
    if not normalized:
        return EmployeeMatchResult(employee=None, code=VacationAttentionCode.MISSING_EMPLOYEE_EMAIL.value)

    listed = await employees.list(
        EmployeeListFilter(organization_id=organization_id, include_disabled=False, limit=500)
    )
    matches = [
        emp
        for emp in listed
        if normalize_email((emp.metadata or {}).get("email")) == normalized
    ]
    if len(matches) == 1:
        return EmployeeMatchResult(employee=matches[0], code=None)
    if len(matches) == 0:
        return EmployeeMatchResult(
            employee=None, code=VacationAttentionCode.EMPLOYEE_NOT_FOUND.value
        )
    return EmployeeMatchResult(
        employee=None, code=VacationAttentionCode.EMPLOYEE_AMBIGUOUS.value
    )


def collect_date_attention_codes(
    start_date: date | None,
    end_date: date | None,
    *,
    require_dates: bool = True,
) -> list[str]:
    codes: list[str] = []
    if start_date is None and require_dates:
        codes.append(VacationAttentionCode.MISSING_START_DATE.value)
    if end_date is None and require_dates:
        codes.append(VacationAttentionCode.MISSING_END_DATE.value)
    if start_date is not None and end_date is not None and end_date < start_date:
        codes.append(VacationAttentionCode.END_BEFORE_START.value)
    return codes


async def find_overlaps(
    vacations: VacationRequestRepository,
    organization_id: UUID,
    *,
    employee_id: UUID,
    start_date: date | None,
    end_date: date | None,
    exclude_id: UUID | None = None,
) -> list[VacationRequest]:
    if employee_id is None or start_date is None or end_date is None:
        return []
    existing = await vacations.list_for_employee(organization_id, employee_id)
    overlaps: list[VacationRequest] = []
    for other in existing:
        if exclude_id and other.id == exclude_id:
            continue
        if other.review_status not in {
            VacationReviewStatus.APPROVED.value,
            VacationReviewStatus.PENDING_APPROVAL.value,
            VacationReviewStatus.REQUIRES_ATTENTION.value,
        }:
            continue
        if other.start_date is None or other.end_date is None:
            continue
        # Exact same dates are business duplicates, not overlaps.
        if other.start_date == start_date and other.end_date == end_date:
            continue
        if intervals_overlap(start_date, end_date, other.start_date, other.end_date):
            overlaps.append(other)
    return overlaps


_ACTIVE_DUPLICATE_STATUSES = frozenset(
    {
        VacationReviewStatus.APPROVED.value,
        VacationReviewStatus.PENDING_APPROVAL.value,
        VacationReviewStatus.REQUIRES_ATTENTION.value,
    }
)


async def find_duplicate_content(
    vacations: VacationRequestRepository,
    organization_id: UUID,
    *,
    employee_id: UUID | None,
    start_date: date | None,
    end_date: date | None,
    exclude_id: UUID | None = None,
) -> VacationRequest | None:
    """Exact employee+dates match among active (non-cancelled/rejected) requests."""
    if employee_id is None or start_date is None or end_date is None:
        return None
    existing = await vacations.list_for_employee(organization_id, employee_id)
    for other in existing:
        if exclude_id and other.id == exclude_id:
            continue
        if other.review_status not in _ACTIVE_DUPLICATE_STATUSES:
            continue
        if other.start_date == start_date and other.end_date == end_date:
            return other
    return None


async def resolve_related_vacation(
    vacations: VacationRequestRepository,
    organization_id: UUID,
    *,
    intent: str,
    employee_id: UUID | None,
    start_date: date | None,
    end_date: date | None,
    target_hints: dict | None = None,
) -> tuple[UUID | None, str | None]:
    """Return (related_id, attention_code) for update/cancel intents."""
    if intent not in {VacationIntent.UPDATE.value, VacationIntent.CANCEL.value}:
        return None, None
    if employee_id is None:
        code = (
            VacationAttentionCode.AMBIGUOUS_UPDATE.value
            if intent == VacationIntent.UPDATE.value
            else VacationAttentionCode.AMBIGUOUS_CANCEL.value
        )
        return None, code

    candidates = await vacations.list_for_employee(organization_id, employee_id)
    openish = [
        v
        for v in candidates
        if v.review_status
        in {
            VacationReviewStatus.APPROVED.value,
            VacationReviewStatus.PENDING_APPROVAL.value,
        }
    ]
    hints = target_hints or {}
    prior_start = hints.get("prior_start")
    prior_end = hints.get("prior_end")
    if prior_start and prior_end:
        matched = [
            v
            for v in openish
            if str(v.start_date) == str(prior_start) and str(v.end_date) == str(prior_end)
        ]
        if len(matched) == 1:
            return matched[0].id, (
                VacationAttentionCode.UPDATE_PROPOSED.value
                if intent == VacationIntent.UPDATE.value
                else VacationAttentionCode.CANCEL_PROPOSED.value
            )
        code = (
            VacationAttentionCode.AMBIGUOUS_UPDATE.value
            if intent == VacationIntent.UPDATE.value
            else VacationAttentionCode.AMBIGUOUS_CANCEL.value
        )
        return None, code

    if start_date and end_date:
        matched = [
            v for v in openish if v.start_date == start_date and v.end_date == end_date
        ]
        if len(matched) == 1:
            return matched[0].id, (
                VacationAttentionCode.UPDATE_PROPOSED.value
                if intent == VacationIntent.UPDATE.value
                else VacationAttentionCode.CANCEL_PROPOSED.value
            )

    if len(openish) == 1:
        return openish[0].id, (
            VacationAttentionCode.UPDATE_PROPOSED.value
            if intent == VacationIntent.UPDATE.value
            else VacationAttentionCode.CANCEL_PROPOSED.value
        )

    code = (
        VacationAttentionCode.AMBIGUOUS_UPDATE.value
        if intent == VacationIntent.UPDATE.value
        else VacationAttentionCode.AMBIGUOUS_CANCEL.value
    )
    return None, code


HARD_BLOCK_CODES = frozenset(
    {
        VacationAttentionCode.MISSING_EMPLOYEE_EMAIL.value,
        VacationAttentionCode.MISSING_START_DATE.value,
        VacationAttentionCode.MISSING_END_DATE.value,
        VacationAttentionCode.INVALID_DATE.value,
        VacationAttentionCode.END_BEFORE_START.value,
        VacationAttentionCode.EMPLOYEE_NOT_FOUND.value,
        VacationAttentionCode.EMPLOYEE_AMBIGUOUS.value,
        VacationAttentionCode.AMBIGUOUS_UPDATE.value,
        VacationAttentionCode.AMBIGUOUS_CANCEL.value,
    }
)

WARNING_CODES = frozenset(
    {
        VacationAttentionCode.OVERLAP.value,
        VacationAttentionCode.DUPLICATE_CONTENT.value,
        VacationAttentionCode.LOW_CONFIDENCE.value,
        VacationAttentionCode.UPDATE_PROPOSED.value,
        VacationAttentionCode.CANCEL_PROPOSED.value,
    }
)


@dataclass(frozen=True, slots=True)
class ApprovalClassification:
    classification: str  # READY | WARNING | BLOCKED
    codes: list[str]
    detail: str | None = None


def classify_for_approval(vacation: VacationRequest) -> ApprovalClassification:
    status = vacation.review_status
    if status in {
        VacationReviewStatus.APPROVED.value,
        VacationReviewStatus.REJECTED.value,
        VacationReviewStatus.CANCELLED.value,
    }:
        return ApprovalClassification(
            classification="BLOCKED",
            codes=["INVALID_STATE_TRANSITION"],
            detail=f"Cannot approve from status {status}",
        )
    if vacation.employee_id is None:
        return ApprovalClassification(
            classification="BLOCKED",
            codes=[VacationAttentionCode.EMPLOYEE_NOT_FOUND.value],
            detail="Employee must be linked before approval",
        )
    codes = list(vacation.attention_codes or [])
    date_codes = collect_date_attention_codes(vacation.start_date, vacation.end_date)
    for code in date_codes:
        if code not in codes:
            codes.append(code)
    hard = [c for c in codes if c in HARD_BLOCK_CODES]
    if hard:
        return ApprovalClassification(classification="BLOCKED", codes=hard)
    warnings = [c for c in codes if c in WARNING_CODES]
    if warnings:
        return ApprovalClassification(classification="WARNING", codes=warnings)
    return ApprovalClassification(classification="READY", codes=[])


def derive_email_automation_status(
    settings: VacationMailboxSettings,
    *,
    has_active_credential: bool,
) -> str:
    """Single authoritative V1 automation status (derived, not a stored flag)."""
    if not has_active_credential:
        return EmailAutomationStatus.NOT_CONFIGURED.value
    if settings.mailbox_connection_status == "error":
        return EmailAutomationStatus.ERROR.value
    if (
        settings.mailbox_connection_status == "ok"
        and normalize_email(settings.active_monitored_email)
    ):
        return EmailAutomationStatus.ACTIVE.value
    return EmailAutomationStatus.DISCONNECTED.value


def build_notification_instructions(
    *,
    settings: VacationMailboxSettings,
    outcome: str,
    durable: bool,
    attention_codes: list[str],
    summary: str,
) -> dict:
    to_email = settings.notification_email_verified or settings.active_monitored_email
    if outcome == "FAILED" or not durable:
        return {
            "should_send": True,
            "mandatory": True,
            "type": "not_stored",
            "severity": "critical",
            "to_email": to_email,
            "subject": "Payroll Copilot: vacation request NOT stored",
            "body_text": summary,
        }
    if outcome == "DUPLICATE":
        return {
            "should_send": False,
            "mandatory": False,
            "type": "duplicate",
            "severity": "info",
            "to_email": to_email,
            "subject": None,
            "body_text": None,
        }
    if outcome == "REQUIRES_ATTENTION" or attention_codes:
        return {
            "should_send": bool(settings.notify_on_error_or_attention),
            "mandatory": False,
            "type": "attention",
            "severity": "warning",
            "to_email": to_email,
            "subject": "Payroll Copilot: vacation needs attention",
            "body_text": summary,
        }
    if outcome == "SUCCESS":
        return {
            "should_send": bool(settings.notify_on_new_vacation),
            "mandatory": False,
            "type": "new_vacation",
            "severity": "info",
            "to_email": to_email,
            "subject": "Payroll Copilot: new vacation request",
            "body_text": summary,
        }
    return {
        "should_send": False,
        "mandatory": False,
        "type": "none",
        "severity": "info",
        "to_email": to_email,
        "subject": None,
        "body_text": None,
    }
