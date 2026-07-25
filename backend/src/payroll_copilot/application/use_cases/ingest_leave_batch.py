"""Batch inbound leave orchestration for n8n (vacation + sick leave)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.vacation_settings import (
    VacationMailboxSettings,
    VacationSettingsRepository,
)
from payroll_copilot.application.services.vacation_rules import normalize_email
from payroll_copilot.application.use_cases.manage_sick_leaves import (
    InboundSickLeaveCommand,
    ManageSickLeavesUseCase,
)
from payroll_copilot.application.use_cases.manage_vacations import (
    InboundVacationCommand,
    ManageVacationsUseCase,
)

logger = logging.getLogger(__name__)

ALLOWED_CLASSIFICATIONS = frozenset({"VACATION", "SICK_LEAVE"})


@dataclass(frozen=True, slots=True)
class InboundLeaveBatchItem:
    provider: str
    provider_message_id: str
    provider_thread_id: str | None
    from_email: str | None
    to_email: str | None
    subject: str | None
    body_text: str | None
    received_at: datetime | None
    classification: str
    intent: str
    employee_email: str | None
    employee_name: str | None
    start_date: str | None
    end_date: str | None
    confidence: float | None
    explanation: str | None
    n8n_attention_codes: list[str]
    target_hints: dict[str, Any] | None = None


def _fmt_date(value: str | date | None) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def _status_label(review_status: str | None, outcome: str) -> str:
    mapping = {
        "pending_approval": "Pending approval",
        "requires_attention": "Requires attention",
        "approved": "Approved",
        "rejected": "Rejected",
        "cancelled": "Cancelled",
    }
    if review_status and review_status in mapping:
        return mapping[review_status]
    if outcome == "REQUIRES_ATTENTION":
        return "Requires attention"
    if outcome == "SUCCESS":
        return "Pending approval"
    if outcome == "FAILED":
        return "Failed"
    return outcome.replace("_", " ").title()


def _attention_summary(codes: list[str]) -> str | None:
    labels = {
        "EMPLOYEE_NOT_FOUND": "Employee could not be matched",
        "EMPLOYEE_AMBIGUOUS": "Multiple employees matched",
        "MISSING_EMPLOYEE_EMAIL": "Employee email missing",
        "MISSING_START_DATE": "Start date missing",
        "MISSING_END_DATE": "End date missing",
        "INVALID_DATE": "Invalid date",
        "END_BEFORE_START": "End date before start date",
        "LOW_CONFIDENCE": "Low AI confidence",
        "OVERLAP": "Overlapping leave dates",
        "AMBIGUOUS_UPDATE": "Ambiguous update target",
        "AMBIGUOUS_CANCEL": "Ambiguous cancel target",
        "UPDATE_PROPOSED": "Update proposed",
        "CANCEL_PROPOSED": "Cancel proposed",
    }
    if not codes:
        return None
    return "; ".join(labels.get(c, c.replace("_", " ").title()) for c in codes)


def build_batch_notification(
    *,
    settings: VacationMailboxSettings,
    results: list[dict[str, Any]],
    duplicate_count: int,
    received_count: int,
) -> dict[str, Any]:
    to_email = normalize_email(settings.notification_email_verified) or normalize_email(
        settings.active_monitored_email
    )

    meaningful = [
        r
        for r in results
        if r.get("outcome") in {"SUCCESS", "REQUIRES_ATTENTION", "FAILED"}
    ]

    if not meaningful or not to_email:
        return {
            "should_send": False,
            "to_email": to_email,
            "subject": None,
            "body_text": None,
        }

    # Preference gating: include an item only if its domain preference allows it.
    notify_rows: list[dict[str, Any]] = []
    for row in meaningful:
        classification = str(row.get("classification") or "").upper()
        outcome = str(row.get("outcome") or "")
        codes = list(row.get("attention_codes") or [])
        if classification == "VACATION":
            if outcome == "FAILED":
                allowed = True
            elif outcome == "REQUIRES_ATTENTION" or codes:
                allowed = bool(settings.notify_on_error_or_attention)
            else:
                allowed = bool(settings.notify_on_new_vacation)
        elif classification == "SICK_LEAVE":
            if outcome == "FAILED":
                allowed = True
            elif outcome == "REQUIRES_ATTENTION" or codes:
                allowed = bool(settings.notify_on_sick_leave_error_or_attention)
            else:
                allowed = bool(settings.notify_on_new_sick_leave)
        else:
            allowed = False
        if allowed:
            notify_rows.append(row)

    if not notify_rows:
        return {
            "should_send": False,
            "to_email": to_email,
            "subject": None,
            "body_text": None,
        }

    lines: list[str] = [
        "Payroll Copilot — New leave requests",
        "",
        f"{received_count} email{'s' if received_count != 1 else ''} were processed.",
    ]
    if duplicate_count:
        lines.append(
            f"{duplicate_count} already-existing request"
            f"{'s' if duplicate_count != 1 else ''} were ignored."
        )
    lines.extend(["", "New / attention-required requests:", ""])

    for idx, row in enumerate(notify_rows, start=1):
        kind = "Vacation" if row.get("classification") == "VACATION" else "Sick Leave"
        name = row.get("employee_name") or row.get("employee_email") or "Unknown employee"
        start = _fmt_date(row.get("start_date"))
        end = _fmt_date(row.get("end_date"))
        status = _status_label(row.get("review_status"), str(row.get("outcome") or ""))
        lines.append(f"{idx}. {kind} — {name}")
        lines.append(f"   {start}–{end}")
        attention = _attention_summary(list(row.get("attention_codes") or []))
        if attention and (
            row.get("outcome") == "REQUIRES_ATTENTION"
            or row.get("review_status") == "requires_attention"
        ):
            lines.append(f"   Requires attention: {attention}.")
        else:
            lines.append(f"   Status: {status}")
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    return {
        "should_send": True,
        "to_email": to_email,
        "subject": "Payroll Copilot — New leave requests",
        "body_text": body,
    }


class IngestLeaveBatchUseCase:
    """Orchestrate mixed VACATION / SICK_LEAVE inbound items into one response."""

    def __init__(
        self,
        *,
        vacations: ManageVacationsUseCase,
        sick_leaves: ManageSickLeavesUseCase,
        settings_repo: VacationSettingsRepository,
    ) -> None:
        self._vacations = vacations
        self._sick_leaves = sick_leaves
        self._settings = settings_repo

    async def execute(
        self,
        organization_id: UUID,
        items: list[InboundLeaveBatchItem],
    ) -> dict[str, Any]:
        settings = await self._settings.get(organization_id)
        results: list[dict[str, Any]] = []
        duplicate_count = 0
        ignored_count = 0
        failed_count = 0

        for raw in items:
            classification = (raw.classification or "").strip().upper()
            try:
                if classification not in ALLOWED_CLASSIFICATIONS:
                    ignored_count += 1
                    results.append(
                        {
                            "classification": classification or "UNKNOWN",
                            "request_id": None,
                            "outcome": "IGNORED",
                            "review_status": None,
                            "employee_name": raw.employee_name,
                            "employee_email": raw.employee_email,
                            "start_date": raw.start_date,
                            "end_date": raw.end_date,
                            "attention_codes": [],
                            "summary": (
                                f"Classification {classification or 'missing'} "
                                "is not accepted by leave batch ingest."
                            ),
                            "summary_code": "IGNORED_CLASSIFICATION",
                        }
                    )
                    continue

                if classification == "VACATION":
                    cmd = InboundVacationCommand(
                        provider=raw.provider,
                        provider_message_id=raw.provider_message_id,
                        provider_thread_id=raw.provider_thread_id,
                        from_email=raw.from_email,
                        to_email=raw.to_email,
                        subject=raw.subject,
                        body_text=raw.body_text,
                        received_at=raw.received_at,
                        classification="VACATION",
                        intent=raw.intent,
                        employee_email=raw.employee_email,
                        employee_name=raw.employee_name,
                        start_date=raw.start_date,
                        end_date=raw.end_date,
                        confidence=raw.confidence,
                        explanation=raw.explanation,
                        n8n_attention_codes=list(raw.n8n_attention_codes or []),
                        target_hints=raw.target_hints,
                    )
                    payload = await self._vacations.ingest_inbound(organization_id, cmd)
                    request_id = payload.get("vacation_request_id")
                else:
                    cmd_s = InboundSickLeaveCommand(
                        provider=raw.provider,
                        provider_message_id=raw.provider_message_id,
                        provider_thread_id=raw.provider_thread_id,
                        from_email=raw.from_email,
                        to_email=raw.to_email,
                        subject=raw.subject,
                        body_text=raw.body_text,
                        received_at=raw.received_at,
                        classification="SICK_LEAVE",
                        intent=raw.intent,
                        employee_email=raw.employee_email,
                        employee_name=raw.employee_name,
                        start_date=raw.start_date,
                        end_date=raw.end_date,
                        confidence=raw.confidence,
                        explanation=raw.explanation,
                        n8n_attention_codes=list(raw.n8n_attention_codes or []),
                        target_hints=raw.target_hints,
                    )
                    payload = await self._sick_leaves.ingest_inbound(
                        organization_id, cmd_s, include_notification=False
                    )
                    request_id = payload.get("sick_leave_request_id")

                outcome = str(payload.get("outcome") or "FAILED")
                if outcome == "DUPLICATE":
                    duplicate_count += 1
                    # Duplicates must not appear as newly stored result entries.
                    continue
                if outcome == "IGNORED":
                    ignored_count += 1
                if outcome == "FAILED":
                    failed_count += 1

                review_status = None
                if request_id and outcome in {"SUCCESS", "REQUIRES_ATTENTION"}:
                    if classification == "VACATION":
                        row = await self._vacations.get_vacation(
                            organization_id, UUID(str(request_id))
                        )
                    else:
                        row = await self._sick_leaves.get_sick_leave(
                            organization_id, UUID(str(request_id))
                        )
                    if row is not None:
                        review_status = row.review_status

                results.append(
                    {
                        "classification": classification,
                        "request_id": request_id,
                        "outcome": outcome,
                        "review_status": review_status,
                        "employee_name": raw.employee_name,
                        "employee_email": raw.employee_email
                        or normalize_email(raw.from_email),
                        "start_date": raw.start_date,
                        "end_date": raw.end_date,
                        "attention_codes": list(payload.get("attention_codes") or []),
                        "summary": payload.get("summary"),
                        "summary_code": payload.get("summary_code"),
                    }
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Leave batch item failed org=%s classification=%s message_id=%s",
                    organization_id,
                    classification,
                    raw.provider_message_id,
                )
                failed_count += 1
                results.append(
                    {
                        "classification": classification or "UNKNOWN",
                        "request_id": None,
                        "outcome": "FAILED",
                        "review_status": None,
                        "employee_name": raw.employee_name,
                        "employee_email": raw.employee_email,
                        "start_date": raw.start_date,
                        "end_date": raw.end_date,
                        "attention_codes": ["BACKEND_PROCESSING_FAILURE"],
                        "summary": (
                            "Payroll Copilot could not process this leave email. "
                            "It was not stored."
                        ),
                        "summary_code": "BACKEND_PROCESSING_FAILURE",
                    }
                )

        notification = build_batch_notification(
            settings=settings,
            results=results,
            duplicate_count=duplicate_count,
            received_count=len(items),
        )
        return {
            "received_count": len(items),
            "duplicate_count": duplicate_count,
            "ignored_count": ignored_count,
            "failed_count": failed_count,
            "result_count": len(results),
            "results": results,
            "notification": notification,
        }
