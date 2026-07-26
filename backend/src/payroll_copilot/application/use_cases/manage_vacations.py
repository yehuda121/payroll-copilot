"""Vacation management use cases — SoT mutations, ingest, settings, OTP, events."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.email import EmailAddress, EmailMessage, EmailService
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository, EmployeeRepository
from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.vacation_requests import (
    VacationListFilter,
    VacationRequestRepository,
)
from payroll_copilot.application.ports.vacation_settings import (
    EmailOwnershipOtp,
    EmailOwnershipOtpRepository,
    IntegrationCredentialRepository,
    VacationMailboxSettings,
    VacationPipelineAnalyticsRepository,
    VacationSettingsRepository,
)
from payroll_copilot.application.services.vacation_rules import (
    HARD_BLOCK_CODES,
    LOW_CONFIDENCE_THRESHOLD,
    MAX_BODY_INLINE_CHARS,
    WARNING_CODES,
    ApprovalClassification,
    build_notification_instructions,
    classify_for_approval,
    collect_date_attention_codes,
    derive_email_automation_status,
    find_duplicate_content,
    find_overlaps,
    match_employee_by_email,
    normalize_email,
    resolve_related_vacation,
)
from payroll_copilot.domain.entities import VacationRequest
from payroll_copilot.domain.enums import (
    LeaveStatusSource,
    VacationAttentionCode,
    VacationIntent,
    VacationPipelineEventType,
    VacationReviewStatus,
    VacationSource,
)
from payroll_copilot.domain.enums import EmployeeStatus

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 12
OTP_MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@dataclass
class InboundVacationCommand:
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


class ManageVacationsUseCase:
    def __init__(
        self,
        *,
        vacations: VacationRequestRepository,
        settings_repo: VacationSettingsRepository,
        otp_repo: EmailOwnershipOtpRepository,
        pipeline: VacationPipelineAnalyticsRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
        email: EmailService,
        object_storage: ObjectStoragePort | None = None,
        credentials: IntegrationCredentialRepository | None = None,
    ) -> None:
        self._vacations = vacations
        self._settings = settings_repo
        self._otp = otp_repo
        self._pipeline = pipeline
        self._employees = employees
        self._audit = audit
        self._email = email
        self._object_storage = object_storage
        self._credentials = credentials

    async def has_active_integration_credential(self, organization_id: UUID) -> bool:
        if self._credentials is None:
            return False
        creds = await self._credentials.list_for_org(organization_id)
        return any(c.revoked_at is None for c in creds)

    async def email_automation_status(self, organization_id: UUID) -> str:
        settings = await self._settings.get(organization_id)
        return derive_email_automation_status(
            settings,
            has_active_credential=await self.has_active_integration_credential(
                organization_id
            ),
        )

    def _enqueue_leave_reconcile(self, organization_id: UUID) -> None:
        try:
            from payroll_copilot.infrastructure.tasks.celery_app import (
                reconcile_employee_leave_status,
            )

            reconcile_employee_leave_status.delay(str(organization_id))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not enqueue leave reconciliation for org %s",
                organization_id,
                exc_info=True,
            )

    @staticmethod
    def _unique_codes(codes: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for code in codes:
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        return out

    @staticmethod
    def _review_status_from_codes(codes: list[str], *, intent: str) -> str:
        hard = set(codes) & HARD_BLOCK_CODES
        if hard or intent in {
            VacationIntent.UPDATE.value,
            VacationIntent.CANCEL.value,
            VacationIntent.UNKNOWN.value,
        }:
            return VacationReviewStatus.REQUIRES_ATTENTION.value
        return VacationReviewStatus.PENDING_APPROVAL.value

    @staticmethod
    def _snapshot_ai_extraction(
        *,
        employee_email: str | None,
        employee_name: str | None,
        start_date: date | None,
        end_date: date | None,
        confidence: float | None,
        explanation: str | None,
    ) -> dict[str, Any]:
        return {
            "employee_email": employee_email,
            "employee_name": employee_name,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "confidence": confidence,
            "explanation": (explanation or "")[:2000] or None,
        }

    async def revalidate_vacation(
        self,
        vac: VacationRequest,
        *,
        rematch_employee: bool = False,
        explicit_employee_id: UUID | None = None,
        explicit_employee_id_set: bool = False,
    ) -> VacationRequest:
        """Recompute match, dates, duplicate/overlap codes, status, and peer overlaps."""
        org_id = vac.organization_id

        if explicit_employee_id_set:
            if explicit_employee_id is None:
                vac.employee_id = None
            else:
                emp = await self._employees.get_by_id(explicit_employee_id)
                if emp is None or emp.organization_id != org_id:
                    raise ValueError("employee_not_found")
                vac.employee_id = explicit_employee_id
        elif rematch_employee:
            match = await match_employee_by_email(
                self._employees, org_id, vac.extracted_employee_email
            )
            vac.employee_id = match.employee.id if match.employee else None

        # Drop identity/date/overlap codes then rebuild from current data.
        volatile = HARD_BLOCK_CODES | WARNING_CODES | {
            VacationAttentionCode.DUPLICATE_CONTENT.value,
            VacationAttentionCode.LOW_CONFIDENCE.value,
            VacationAttentionCode.OVERLAP.value,
        }
        preserved = [c for c in (vac.attention_codes or []) if c not in volatile]
        codes = list(preserved)

        if not vac.extracted_employee_email:
            codes.append(VacationAttentionCode.MISSING_EMPLOYEE_EMAIL.value)
        elif vac.employee_id is None:
            # Rematch when we still lack employee_id
            match = await match_employee_by_email(
                self._employees, org_id, vac.extracted_employee_email
            )
            if match.code:
                codes.append(match.code)
            vac.employee_id = match.employee.id if match.employee else None

        codes.extend(collect_date_attention_codes(vac.start_date, vac.end_date))

        if (
            vac.ai_confidence is not None
            and vac.ai_confidence < LOW_CONFIDENCE_THRESHOLD
            and vac.source == VacationSource.EMAIL.value
        ):
            codes.append(VacationAttentionCode.LOW_CONFIDENCE.value)

        if vac.intent in {VacationIntent.UPDATE.value, VacationIntent.CANCEL.value}:
            if vac.related_vacation_id is None:
                codes.append(
                    VacationAttentionCode.AMBIGUOUS_UPDATE.value
                    if vac.intent == VacationIntent.UPDATE.value
                    else VacationAttentionCode.AMBIGUOUS_CANCEL.value
                )
            else:
                codes.append(
                    VacationAttentionCode.UPDATE_PROPOSED.value
                    if vac.intent == VacationIntent.UPDATE.value
                    else VacationAttentionCode.CANCEL_PROPOSED.value
                )

        overlaps: list[VacationRequest] = []
        if vac.employee_id and vac.start_date and vac.end_date:
            dup = await find_duplicate_content(
                self._vacations,
                org_id,
                employee_id=vac.employee_id,
                start_date=vac.start_date,
                end_date=vac.end_date,
                exclude_id=vac.id,
            )
            if dup:
                codes.append(VacationAttentionCode.DUPLICATE_CONTENT.value)
            overlaps = await find_overlaps(
                self._vacations,
                org_id,
                employee_id=vac.employee_id,
                start_date=vac.start_date,
                end_date=vac.end_date,
                exclude_id=vac.id,
            )
            if overlaps:
                codes.append(VacationAttentionCode.OVERLAP.value)

        vac.attention_codes = self._unique_codes(codes)
        vac.overlap_with = [o.id for o in overlaps]
        if vac.review_status not in {
            VacationReviewStatus.APPROVED.value,
            VacationReviewStatus.REJECTED.value,
            VacationReviewStatus.CANCELLED.value,
        }:
            vac.review_status = self._review_status_from_codes(
                vac.attention_codes, intent=vac.intent
            )
        return vac

    async def _refresh_overlap_peers(
        self,
        organization_id: UUID,
        *,
        employee_id: UUID | None,
        exclude_id: UUID | None = None,
        previous_peer_ids: list[UUID] | None = None,
    ) -> None:
        """Recompute OVERLAP on peers that may have changed due to this write."""
        peer_ids: set[UUID] = set(previous_peer_ids or [])
        if employee_id is not None:
            for peer in await self._vacations.list_for_employee(organization_id, employee_id):
                peer_ids.add(peer.id)
        for peer_id in peer_ids:
            if exclude_id and peer_id == exclude_id:
                continue
            peer = await self._vacations.get_by_id(organization_id, peer_id)
            if peer is None:
                continue
            if peer.review_status in {
                VacationReviewStatus.REJECTED.value,
                VacationReviewStatus.CANCELLED.value,
            }:
                continue
            await self.revalidate_vacation(peer, rematch_employee=False)
            await self._vacations.save(peer)

    # ---- settings / OTP -------------------------------------------------

    async def get_settings(self, organization_id: UUID) -> VacationMailboxSettings:
        return await self._settings.get(organization_id)

    async def patch_preferences(
        self,
        organization_id: UUID,
        *,
        actor_user_id: UUID | None,
        notify_on_new_vacation: bool | None = None,
        notify_on_error_or_attention: bool | None = None,
        notify_on_new_sick_leave: bool | None = None,
        notify_on_sick_leave_error_or_attention: bool | None = None,
        notification_email: str | None = None,
        update_notification_email: bool = False,
    ) -> VacationMailboxSettings:
        """Patch notification prefs and optionally the notification destination email.

        When ``update_notification_email`` is True, ``notification_email`` (empty → clear)
        is written to ``notification_email_verified`` without OTP. Sending still falls back
        to ``active_monitored_email`` when verified is unset; OTP endpoints remain for
        backward compatibility but are unused by the V1 accountant UI.
        """
        settings = await self._settings.get(organization_id)
        if notify_on_new_vacation is not None:
            settings.notify_on_new_vacation = notify_on_new_vacation
        if notify_on_error_or_attention is not None:
            settings.notify_on_error_or_attention = notify_on_error_or_attention
        if notify_on_new_sick_leave is not None:
            settings.notify_on_new_sick_leave = notify_on_new_sick_leave
        if notify_on_sick_leave_error_or_attention is not None:
            settings.notify_on_sick_leave_error_or_attention = (
                notify_on_sick_leave_error_or_attention
            )
        if update_notification_email:
            cleaned = normalize_email(notification_email)
            if cleaned is None:
                settings.notification_email_verified = None
                settings.notification_email_pending = None
            else:
                # Basic local@domain structure — no deliverability check.
                local, _, domain = cleaned.partition("@")
                if not local or not domain or "." not in domain or " " in cleaned:
                    raise ValueError("invalid_email")
                settings.notification_email_verified = cleaned
                settings.notification_email_pending = None
        saved = await self._settings.save(settings)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.settings_updated",
                resource_type="vacation_settings",
                organization_id=organization_id,
                user_id=actor_user_id,
                details={
                    "notify_on_new_vacation": saved.notify_on_new_vacation,
                    "notify_on_error_or_attention": saved.notify_on_error_or_attention,
                    "notify_on_new_sick_leave": saved.notify_on_new_sick_leave,
                    "notify_on_sick_leave_error_or_attention": (
                        saved.notify_on_sick_leave_error_or_attention
                    ),
                    "notification_email_verified": saved.notification_email_verified,
                },
            )
        )
        return saved

    async def start_email_verification(
        self,
        organization_id: UUID,
        *,
        purpose: str,
        email: str,
        actor_user_id: UUID | None,
    ) -> dict[str, Any]:
        purpose = purpose.strip().lower()
        if purpose == "monitored":
            raise ValueError("monitored_otp_retired")
        if purpose != "notification":
            raise ValueError("invalid_purpose")
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise ValueError("invalid_email")

        settings = await self._settings.get(organization_id)
        settings.notification_email_pending = normalized
        await self._settings.save(settings)

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp = EmailOwnershipOtp(
            organization_id=organization_id,
            purpose=purpose,
            email=normalized,
            code_hash=_hash_otp(code),
            expires_at=_now() + timedelta(minutes=OTP_TTL_MINUTES),
            attempts=0,
            max_attempts=OTP_MAX_ATTEMPTS,
            created_at=_now(),
        )
        await self._otp.save(otp)

        await self._email.send(
            EmailMessage(
                to=[EmailAddress(email=normalized)],
                subject="Payroll Copilot email verification code",
                text_body=(
                    f"Your verification code is: {code}\n\n"
                    f"It expires in {OTP_TTL_MINUTES} minutes.\n"
                    "If you did not request this, ignore this message."
                ),
                tags={"purpose": purpose, "org": str(organization_id)},
            )
        )
        logger.info(
            "vacation_otp_sent purpose=%s org=%s email_domain=%s",
            purpose,
            organization_id,
            normalized.split("@")[-1],
        )
        await self._audit.append(
            AuditLogEntry(
                action="vacation.email_otp_started",
                resource_type="vacation_settings",
                organization_id=organization_id,
                user_id=actor_user_id,
                details={"purpose": purpose, "email": normalized},
            )
        )
        return {"purpose": purpose, "email": normalized, "expires_in_seconds": OTP_TTL_MINUTES * 60}

    async def confirm_email_verification(
        self,
        organization_id: UUID,
        *,
        purpose: str,
        email: str,
        code: str,
        actor_user_id: UUID | None,
    ) -> VacationMailboxSettings:
        purpose = purpose.strip().lower()
        if purpose == "monitored":
            raise ValueError("monitored_otp_retired")
        if purpose != "notification":
            raise ValueError("invalid_purpose")
        normalized = normalize_email(email)
        if not normalized:
            raise ValueError("invalid_email")
        otp = await self._otp.get(organization_id, purpose=purpose, email=normalized)
        if otp is None:
            raise ValueError("otp_not_found")
        if otp.expires_at < _now():
            await self._otp.delete(organization_id, purpose=purpose, email=normalized)
            raise ValueError("otp_expired")
        if otp.attempts >= otp.max_attempts:
            raise ValueError("otp_attempts_exceeded")
        if _hash_otp(code.strip()) != otp.code_hash:
            otp.attempts += 1
            await self._otp.save(otp)
            raise ValueError("otp_invalid")

        await self._otp.delete(organization_id, purpose=purpose, email=normalized)
        settings = await self._settings.get(organization_id)
        settings.notification_email_verified = normalized
        settings.notification_email_pending = None
        saved = await self._settings.save(settings)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.email_verified",
                resource_type="vacation_settings",
                organization_id=organization_id,
                user_id=actor_user_id,
                details={"purpose": purpose, "email": normalized},
            )
        )
        return saved

    async def apply_mailbox_health(
        self,
        organization_id: UUID,
        *,
        monitored_email: str,
        status: str,
        checked_at: datetime | None,
        last_processed_at: datetime | None,
        last_processed_message_id: str | None,
        error_code: str | None,
        error_message: str | None,
    ) -> VacationMailboxSettings:
        settings = await self._settings.get(organization_id)
        email = normalize_email(monitored_email)
        settings.mailbox_last_check_at = checked_at or _now()
        if last_processed_at:
            settings.mailbox_last_processed_at = last_processed_at
        if last_processed_message_id:
            settings.mailbox_last_processed_message_id = last_processed_message_id
        if status == "ok":
            settings.mailbox_connection_status = "ok"
            settings.mailbox_last_error_code = None
            settings.mailbox_last_error_message = None
            # V1: health is the SoT for displayed monitored mailbox (no OTP dual-gate).
            if email:
                settings.active_monitored_email = email
        else:
            settings.mailbox_connection_status = "error"
            settings.mailbox_last_error_code = (error_code or "connection_error")[:64]
            settings.mailbox_last_error_message = (error_message or "")[:500]
        return await self._settings.save(settings)

    async def mailbox_config_for_n8n(self, settings: VacationMailboxSettings) -> dict[str, Any]:
        status = derive_email_automation_status(
            settings,
            has_active_credential=await self.has_active_integration_credential(
                settings.organization_id
            ),
        )
        return {
            "organization_id": str(settings.organization_id),
            "email_automation_status": status,
            "notification_email": settings.notification_email_verified,
            "prefs": {
                "notify_on_new_vacation": settings.notify_on_new_vacation,
                "notify_on_error_or_attention": settings.notify_on_error_or_attention,
            },
        }

    # ---- CRUD / list ----------------------------------------------------

    async def list_vacations(
        self, organization_id: UUID, **kwargs: Any
    ) -> list[VacationRequest]:
        return await self._vacations.list(
            VacationListFilter(organization_id=organization_id, **kwargs)
        )

    async def get_vacation(
        self, organization_id: UUID, vacation_id: UUID
    ) -> VacationRequest | None:
        return await self._vacations.get_by_id(organization_id, vacation_id)

    async def create_manual(
        self,
        organization_id: UUID,
        *,
        actor_user_id: UUID | None,
        employee_id: UUID | None,
        employee_email: str | None,
        employee_name: str | None,
        start_date: date,
        end_date: date,
        subject: str | None = None,
        notes: str | None = None,
    ) -> VacationRequest:
        codes = collect_date_attention_codes(start_date, end_date)
        if employee_id is not None:
            emp = await self._employees.get_by_id(employee_id)
            if emp is None or emp.organization_id != organization_id:
                raise ValueError("employee_not_found")
        match = await match_employee_by_email(
            self._employees, organization_id, employee_email
        )
        linked = employee_id or (match.employee.id if match.employee else None)
        if employee_id is None and match.code:
            codes.append(match.code)
        if linked:
            overlaps = await find_overlaps(
                self._vacations,
                organization_id,
                employee_id=linked,
                start_date=start_date,
                end_date=end_date,
            )
            if overlaps:
                codes.append(VacationAttentionCode.OVERLAP.value)
        status = (
            VacationReviewStatus.REQUIRES_ATTENTION.value
            if any(c in codes for c in (
                VacationAttentionCode.EMPLOYEE_NOT_FOUND.value,
                VacationAttentionCode.EMPLOYEE_AMBIGUOUS.value,
                VacationAttentionCode.END_BEFORE_START.value,
                VacationAttentionCode.MISSING_START_DATE.value,
                VacationAttentionCode.MISSING_END_DATE.value,
            ))
            else VacationReviewStatus.PENDING_APPROVAL.value
        )
        vac = VacationRequest(
            id=uuid4(),
            organization_id=organization_id,
            employee_id=linked,
            extracted_employee_email=normalize_email(employee_email),
            extracted_employee_name=employee_name,
            start_date=start_date,
            end_date=end_date,
            source=VacationSource.MANUAL.value,
            intent=VacationIntent.NEW.value,
            review_status=status,
            attention_codes=codes,
            attention_detail=notes,
            original_subject=subject or "Manual vacation",
            original_body_text=notes,
            ai_confidence=1.0,
            created_by=actor_user_id,
            created_at=_now(),
            updated_at=_now(),
        )
        saved = await self._vacations.save(vac)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.created_manual",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                user_id=actor_user_id,
                details={"start_date": str(start_date), "end_date": str(end_date)},
            )
        )
        return saved

    async def update_vacation(
        self,
        organization_id: UUID,
        vacation_id: UUID,
        *,
        actor_user_id: UUID | None,
        **fields: Any,
    ) -> VacationRequest:
        vac = await self._vacations.get_by_id(organization_id, vacation_id)
        if vac is None:
            raise ValueError("not_found")

        before = {
            "extracted_employee_email": vac.extracted_employee_email,
            "extracted_employee_name": vac.extracted_employee_name,
            "start_date": vac.start_date.isoformat() if vac.start_date else None,
            "end_date": vac.end_date.isoformat() if vac.end_date else None,
            "employee_id": str(vac.employee_id) if vac.employee_id else None,
            "review_status": vac.review_status,
            "attention_codes": list(vac.attention_codes or []),
        }
        previous_peers = list(vac.overlap_with or [])
        previous_employee_id = vac.employee_id

        rematch = False
        explicit_set = False
        explicit_id: UUID | None = None

        if "start_date" in fields:
            vac.start_date = fields["start_date"]
        if "end_date" in fields:
            vac.end_date = fields["end_date"]
        if "extracted_employee_email" in fields:
            vac.extracted_employee_email = normalize_email(fields["extracted_employee_email"])
            rematch = True
        if "extracted_employee_name" in fields:
            vac.extracted_employee_name = fields["extracted_employee_name"]
        if "employee_id" in fields:
            explicit_set = True
            explicit_id = fields["employee_id"]
        if "attention_detail" in fields:
            vac.attention_detail = fields["attention_detail"]

        # Never overwrite immutable AI snapshot.
        await self.revalidate_vacation(
            vac,
            rematch_employee=rematch and not explicit_set,
            explicit_employee_id=explicit_id,
            explicit_employee_id_set=explicit_set,
        )
        saved = await self._vacations.save(vac)
        await self._refresh_overlap_peers(
            organization_id,
            employee_id=saved.employee_id or previous_employee_id,
            exclude_id=saved.id,
            previous_peer_ids=previous_peers,
        )

        after = {
            "extracted_employee_email": saved.extracted_employee_email,
            "extracted_employee_name": saved.extracted_employee_name,
            "start_date": saved.start_date.isoformat() if saved.start_date else None,
            "end_date": saved.end_date.isoformat() if saved.end_date else None,
            "employee_id": str(saved.employee_id) if saved.employee_id else None,
            "review_status": saved.review_status,
            "attention_codes": list(saved.attention_codes or []),
        }
        await self._audit.append(
            AuditLogEntry(
                action="vacation.updated",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                user_id=actor_user_id,
                details={
                    "fields": list(fields.keys()),
                    "before": before,
                    "after": after,
                },
            )
        )
        return saved

    async def cancel_or_delete(
        self,
        organization_id: UUID,
        vacation_id: UUID,
        *,
        actor_user_id: UUID | None,
    ) -> VacationRequest | None:
        vac = await self._vacations.get_by_id(organization_id, vacation_id)
        if vac is None:
            raise ValueError("not_found")
        previous_peers = list(vac.overlap_with or [])
        previous_employee_id = vac.employee_id
        if vac.review_status == VacationReviewStatus.APPROVED.value:
            vac.review_status = VacationReviewStatus.CANCELLED.value
            vac.attention_codes = [
                c
                for c in (vac.attention_codes or [])
                if c != VacationAttentionCode.OVERLAP.value
            ]
            vac.overlap_with = []
            saved = await self._vacations.save(vac)
            await self._audit.append(
                AuditLogEntry(
                    action="vacation.cancelled",
                    resource_type="vacation_request",
                    resource_id=saved.id,
                    organization_id=organization_id,
                    user_id=actor_user_id,
                )
            )
            await self._refresh_overlap_peers(
                organization_id,
                employee_id=previous_employee_id,
                exclude_id=saved.id,
                previous_peer_ids=previous_peers,
            )
            self._enqueue_leave_reconcile(organization_id)
            return saved
        await self._vacations.delete(organization_id, vacation_id)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.deleted",
                resource_type="vacation_request",
                resource_id=vacation_id,
                organization_id=organization_id,
                user_id=actor_user_id,
            )
        )
        await self._refresh_overlap_peers(
            organization_id,
            employee_id=previous_employee_id,
            exclude_id=vacation_id,
            previous_peer_ids=previous_peers,
        )
        self._enqueue_leave_reconcile(organization_id)
        return None

    async def bulk_delete(
        self,
        organization_id: UUID,
        vacation_ids: list[UUID],
        *,
        actor_user_id: UUID | None,
    ) -> dict[str, Any]:
        deleted: list[dict[str, str]] = []
        cancelled: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        for vid in vacation_ids:
            try:
                result = await self.cancel_or_delete(
                    organization_id, vid, actor_user_id=actor_user_id
                )
                if result is None:
                    deleted.append({"id": str(vid)})
                else:
                    cancelled.append({"id": str(vid)})
            except ValueError as exc:
                failed.append({"id": str(vid), "error": str(exc) or "failed"})
            except Exception as exc:  # noqa: BLE001
                failed.append({"id": str(vid), "error": type(exc).__name__})
        await self._audit.append(
            AuditLogEntry(
                action="vacation.bulk_deleted",
                resource_type="vacation_request",
                organization_id=organization_id,
                user_id=actor_user_id,
                details={
                    "deleted": [row["id"] for row in deleted],
                    "cancelled": [row["id"] for row in cancelled],
                    "failed": failed,
                },
            )
        )
        return {
            "status": "completed",
            "deleted": deleted,
            "cancelled": cancelled,
            "failed": failed,
        }

    async def link_employee(
        self,
        organization_id: UUID,
        vacation_id: UUID,
        *,
        employee_id: UUID,
        actor_user_id: UUID | None,
    ) -> VacationRequest:
        vac = await self._vacations.get_by_id(organization_id, vacation_id)
        if vac is None:
            raise ValueError("not_found")
        emp = await self._employees.get_by_id(employee_id)
        if emp is None or emp.organization_id != organization_id:
            raise ValueError("employee_not_found")
        vac.employee_id = employee_id
        vac.attention_codes = [
            c
            for c in vac.attention_codes
            if c
            not in {
                VacationAttentionCode.EMPLOYEE_NOT_FOUND.value,
                VacationAttentionCode.EMPLOYEE_AMBIGUOUS.value,
                VacationAttentionCode.MISSING_EMPLOYEE_EMAIL.value,
            }
        ]
        if not vac.extracted_employee_email:
            vac.extracted_employee_email = normalize_email((emp.metadata or {}).get("email"))
        if vac.review_status == VacationReviewStatus.REQUIRES_ATTENTION.value:
            remaining_hard = [
                c
                for c in vac.attention_codes
                if c
                in {
                    VacationAttentionCode.MISSING_START_DATE.value,
                    VacationAttentionCode.MISSING_END_DATE.value,
                    VacationAttentionCode.END_BEFORE_START.value,
                    VacationAttentionCode.INVALID_DATE.value,
                    VacationAttentionCode.AMBIGUOUS_UPDATE.value,
                    VacationAttentionCode.AMBIGUOUS_CANCEL.value,
                }
            ]
            if not remaining_hard:
                vac.review_status = VacationReviewStatus.PENDING_APPROVAL.value
        saved = await self._vacations.save(vac)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.employee_linked",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                user_id=actor_user_id,
                details={"employee_id": str(employee_id)},
            )
        )
        return saved

    # ---- approval -------------------------------------------------------

    async def classify_approval(
        self, organization_id: UUID, vacation_id: UUID
    ) -> tuple[VacationRequest, ApprovalClassification]:
        vac = await self._vacations.get_by_id(organization_id, vacation_id)
        if vac is None:
            raise ValueError("not_found")
        # Refresh overlap / duplicate warnings
        if vac.employee_id and vac.start_date and vac.end_date:
            overlaps = await find_overlaps(
                self._vacations,
                organization_id,
                employee_id=vac.employee_id,
                start_date=vac.start_date,
                end_date=vac.end_date,
                exclude_id=vac.id,
            )
            codes = [c for c in vac.attention_codes if c != VacationAttentionCode.OVERLAP.value]
            if overlaps:
                codes.append(VacationAttentionCode.OVERLAP.value)
            dup = await find_duplicate_content(
                self._vacations,
                organization_id,
                employee_id=vac.employee_id,
                start_date=vac.start_date,
                end_date=vac.end_date,
                exclude_id=vac.id,
            )
            codes = [c for c in codes if c != VacationAttentionCode.DUPLICATE_CONTENT.value]
            if dup:
                codes.append(VacationAttentionCode.DUPLICATE_CONTENT.value)
            vac.attention_codes = codes
        return vac, classify_for_approval(vac)

    async def approve(
        self,
        organization_id: UUID,
        vacation_id: UUID,
        *,
        actor_user_id: UUID | None,
        confirm_warnings: bool = False,
        apply_update_cancel: bool = True,
    ) -> VacationRequest:
        vac, classification = await self.classify_approval(organization_id, vacation_id)
        if classification.classification == "BLOCKED":
            raise ValueError(f"blocked:{','.join(classification.codes)}")
        if classification.classification == "WARNING" and not confirm_warnings:
            raise ValueError(f"confirmation_required:{','.join(classification.codes)}")

        # Apply linked update/cancel proposals explicitly on approval
        if apply_update_cancel and vac.related_vacation_id and vac.intent in {
            VacationIntent.UPDATE.value,
            VacationIntent.CANCEL.value,
        }:
            target = await self._vacations.get_by_id(organization_id, vac.related_vacation_id)
            if target is not None:
                if vac.intent == VacationIntent.CANCEL.value:
                    target.review_status = VacationReviewStatus.CANCELLED.value
                    await self._vacations.save(target)
                elif vac.intent == VacationIntent.UPDATE.value:
                    if vac.start_date:
                        target.start_date = vac.start_date
                    if vac.end_date:
                        target.end_date = vac.end_date
                    await self._vacations.save(target)

        vac.review_status = VacationReviewStatus.APPROVED.value
        vac.approved_by = actor_user_id
        vac.approved_at = _now()
        vac.attention_codes = [
            c
            for c in vac.attention_codes
            if c
            not in {
                VacationAttentionCode.OVERLAP.value,
                VacationAttentionCode.DUPLICATE_CONTENT.value,
                VacationAttentionCode.LOW_CONFIDENCE.value,
                VacationAttentionCode.UPDATE_PROPOSED.value,
                VacationAttentionCode.CANCEL_PROPOSED.value,
            }
        ]
        saved = await self._vacations.save(vac)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.approved",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                user_id=actor_user_id,
                details={"confirm_warnings": confirm_warnings},
            )
        )
        self._enqueue_leave_reconcile(organization_id)
        return saved

    async def reject(
        self,
        organization_id: UUID,
        vacation_id: UUID,
        *,
        actor_user_id: UUID | None,
        reason: str | None = None,
    ) -> VacationRequest:
        vac = await self._vacations.get_by_id(organization_id, vacation_id)
        if vac is None:
            raise ValueError("not_found")
        vac.review_status = VacationReviewStatus.REJECTED.value
        if reason:
            vac.attention_detail = reason
        saved = await self._vacations.save(vac)
        await self._audit.append(
            AuditLogEntry(
                action="vacation.rejected",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                user_id=actor_user_id,
            )
        )
        return saved

    async def bulk_approve(
        self,
        organization_id: UUID,
        vacation_ids: list[UUID],
        *,
        actor_user_id: UUID | None,
        confirm_warnings: bool = False,
    ) -> dict[str, Any]:
        preview: list[dict[str, Any]] = []
        for vid in vacation_ids:
            try:
                vac, classification = await self.classify_approval(organization_id, vid)
                preview.append(
                    {
                        "id": str(vid),
                        "classification": classification.classification,
                        "codes": classification.codes,
                        "detail": classification.detail,
                        "employee_id": str(vac.employee_id) if vac.employee_id else None,
                    }
                )
            except ValueError:
                preview.append(
                    {
                        "id": str(vid),
                        "classification": "BLOCKED",
                        "codes": ["NOT_FOUND"],
                        "detail": "Vacation not found",
                        "employee_id": None,
                    }
                )

        if not confirm_warnings and any(p["classification"] == "WARNING" for p in preview):
            return {
                "status": "confirmation_required",
                "items": preview,
                "approved": [],
                "skipped_blocked": [p for p in preview if p["classification"] == "BLOCKED"],
                "failed": [],
            }

        approved: list[dict[str, Any]] = []
        skipped = [p for p in preview if p["classification"] == "BLOCKED"]
        failed: list[dict[str, Any]] = []
        for item in preview:
            if item["classification"] == "BLOCKED":
                continue
            if item["classification"] == "WARNING" and not confirm_warnings:
                continue
            try:
                vac = await self.approve(
                    organization_id,
                    UUID(item["id"]),
                    actor_user_id=actor_user_id,
                    confirm_warnings=True,
                )
                approved.append({"id": str(vac.id), "status": vac.review_status})
            except Exception as exc:  # noqa: BLE001
                failed.append({"id": item["id"], "error": str(exc)})

        await self._audit.append(
            AuditLogEntry(
                action="vacation.bulk_approved",
                resource_type="vacation_request",
                organization_id=organization_id,
                user_id=actor_user_id,
                details={
                    "requested": len(vacation_ids),
                    "approved": len(approved),
                    "skipped": len(skipped),
                    "failed": len(failed),
                    "confirm_warnings": confirm_warnings,
                },
            )
        )
        return {
            "status": (
                "partial"
                if failed or (skipped and approved)
                else ("completed" if approved else "no_approvals")
            ),
            "items": preview,
            "approved": approved,
            "skipped_blocked": skipped,
            "failed": failed,
        }

    async def unseen_count(self, organization_id: UUID) -> int:
        return await self._vacations.count_unseen(organization_id)

    async def mark_seen(
        self,
        organization_id: UUID,
        *,
        vacation_ids: list[UUID] | None = None,
        seen_before: datetime | None = None,
    ) -> int:
        return await self._vacations.mark_seen(
            organization_id,
            vacation_ids=vacation_ids,
            seen_before=seen_before,
            seen_at=_now(),
        )

    # ---- ingest ---------------------------------------------------------

    async def ingest_inbound(
        self, organization_id: UUID, command: InboundVacationCommand
    ) -> dict[str, Any]:
        settings = await self._settings.get(organization_id)
        provider = (command.provider or "gmail").strip().lower()
        message_id = (command.provider_message_id or "").strip()
        if not message_id:
            summary = "Inbound vacation rejected: missing provider_message_id. NOT stored."
            return {
                "outcome": "FAILED",
                "durable": False,
                "vacation_request_id": None,
                "attention_codes": ["INVALID_PROVIDER_MESSAGE_ID"],
                "summary_code": "INVALID_PROVIDER_MESSAGE_ID",
                "summary": summary,
                "notification": build_notification_instructions(
                    settings=settings,
                    outcome="FAILED",
                    durable=False,
                    attention_codes=[],
                    summary=summary,
                ),
                "prefs_echo": {
                    "notify_on_new_vacation": settings.notify_on_new_vacation,
                    "notify_on_error_or_attention": settings.notify_on_error_or_attention,
                },
            }

        existing = await self._vacations.get_by_provider_message(
            organization_id, provider=provider, provider_message_id=message_id
        )
        if existing is not None:
            summary = "Duplicate provider message; existing vacation returned."
            return {
                "outcome": "DUPLICATE",
                "durable": True,
                "vacation_request_id": str(existing.id),
                "attention_codes": [],
                "summary_code": "DUPLICATE_PROVIDER_MESSAGE",
                "summary": summary,
                "notification": build_notification_instructions(
                    settings=settings,
                    outcome="DUPLICATE",
                    durable=True,
                    attention_codes=[],
                    summary=summary,
                ),
                "prefs_echo": {
                    "notify_on_new_vacation": settings.notify_on_new_vacation,
                    "notify_on_error_or_attention": settings.notify_on_error_or_attention,
                },
            }

        classification = (command.classification or "VACATION").upper()
        if classification != "VACATION":
            summary = f"Classification {classification} ignored by vacation ingest."
            return {
                "outcome": "IGNORED",
                "durable": False,
                "vacation_request_id": None,
                "attention_codes": [],
                "summary_code": "IGNORED_CLASSIFICATION",
                "summary": summary,
                "notification": build_notification_instructions(
                    settings=settings,
                    outcome="IGNORED",
                    durable=False,
                    attention_codes=[],
                    summary=summary,
                ),
                "prefs_echo": {
                    "notify_on_new_vacation": settings.notify_on_new_vacation,
                    "notify_on_error_or_attention": settings.notify_on_error_or_attention,
                },
            }

        start = _parse_date(command.start_date)
        end = _parse_date(command.end_date)
        codes = list(command.n8n_attention_codes or [])
        if command.start_date and start is None:
            codes.append(VacationAttentionCode.INVALID_DATE.value)
        if command.end_date and end is None:
            codes.append(VacationAttentionCode.INVALID_DATE.value)
        codes.extend(collect_date_attention_codes(start, end))

        email = normalize_email(command.employee_email) or normalize_email(command.from_email)
        match = await match_employee_by_email(self._employees, organization_id, email)
        if match.code:
            codes.append(match.code)
        employee_id = match.employee.id if match.employee else None

        confidence = command.confidence
        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            codes.append(VacationAttentionCode.LOW_CONFIDENCE.value)

        if employee_id and start and end:
            overlaps = await find_overlaps(
                self._vacations,
                organization_id,
                employee_id=employee_id,
                start_date=start,
                end_date=end,
            )
            if overlaps:
                codes.append(VacationAttentionCode.OVERLAP.value)
            intent_early = (command.intent or VacationIntent.NEW.value).lower()
            if intent_early not in {i.value for i in VacationIntent}:
                intent_early = VacationIntent.UNKNOWN.value
            # Suppress exact duplicates only for NEW leave requests (not update/cancel).
            if intent_early == VacationIntent.NEW.value:
                dup = await find_duplicate_content(
                    self._vacations,
                    organization_id,
                    employee_id=employee_id,
                    start_date=start,
                    end_date=end,
                )
                if dup:
                    summary = (
                        "Exact business duplicate of an existing leave request; "
                        "existing vacation returned."
                    )
                    return {
                        "outcome": "DUPLICATE",
                        "durable": True,
                        "vacation_request_id": str(dup.id),
                        "attention_codes": [],
                        "summary_code": "DUPLICATE_CONTENT",
                        "summary": summary,
                        "notification": build_notification_instructions(
                            settings=settings,
                            outcome="DUPLICATE",
                            durable=True,
                            attention_codes=[],
                            summary=summary,
                        ),
                        "prefs_echo": {
                            "notify_on_new_vacation": settings.notify_on_new_vacation,
                            "notify_on_error_or_attention": settings.notify_on_error_or_attention,
                        },
                    }

        intent = (command.intent or VacationIntent.NEW.value).lower()
        if intent not in {i.value for i in VacationIntent}:
            intent = VacationIntent.UNKNOWN.value
        related_id, related_code = await resolve_related_vacation(
            self._vacations,
            organization_id,
            intent=intent,
            employee_id=employee_id,
            start_date=start,
            end_date=end,
            target_hints=command.target_hints,
        )
        if related_code:
            codes.append(related_code)

        uniq_codes = self._unique_codes(codes)
        # Warning-only codes stay pending_approval; hard blockers require attention.
        needs_attention = bool(set(uniq_codes) & HARD_BLOCK_CODES) or intent in {
            VacationIntent.UPDATE.value,
            VacationIntent.CANCEL.value,
            VacationIntent.UNKNOWN.value,
        }
        status = (
            VacationReviewStatus.REQUIRES_ATTENTION.value
            if needs_attention
            else VacationReviewStatus.PENDING_APPROVAL.value
        )

        body = command.body_text or ""
        body_s3 = None
        if len(body) > MAX_BODY_INLINE_CHARS:
            full_body = body
            body = body[:MAX_BODY_INLINE_CHARS]
            if self._object_storage is not None:
                try:
                    key = (
                        f"vacations/{organization_id}/{provider}/"
                        f"{message_id[:200]}.txt"
                    )
                    await self._object_storage.upload(
                        key, full_body.encode("utf-8"), "text/plain; charset=utf-8"
                    )
                    body_s3 = key
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to upload oversized vacation body to S3; "
                        "keeping truncated inline preview only",
                        exc_info=True,
                    )

        explanation = (command.explanation or "")[:2000] or None
        vac = VacationRequest(
            id=uuid4(),
            organization_id=organization_id,
            employee_id=employee_id,
            extracted_employee_email=email,
            extracted_employee_name=command.employee_name,
            sender_email=normalize_email(command.from_email),
            start_date=start,
            end_date=end,
            provider=provider,
            provider_message_id=message_id,
            provider_thread_id=command.provider_thread_id,
            original_subject=(command.subject or "")[:500],
            original_body_text=body,
            original_body_s3_key=body_s3,
            received_at=command.received_at or _now(),
            ai_confidence=confidence,
            ai_explanation=explanation,
            ai_extraction_original=self._snapshot_ai_extraction(
                employee_email=email,
                employee_name=command.employee_name,
                start_date=start,
                end_date=end,
                confidence=confidence,
                explanation=explanation,
            ),
            intent=intent,
            related_vacation_id=related_id,
            source=VacationSource.EMAIL.value,
            review_status=status,
            attention_codes=uniq_codes,
            overlap_with=[],
            created_at=_now(),
            updated_at=_now(),
        )
        if vac.employee_id and vac.start_date and vac.end_date:
            peer_overlaps = await find_overlaps(
                self._vacations,
                organization_id,
                employee_id=vac.employee_id,
                start_date=vac.start_date,
                end_date=vac.end_date,
                exclude_id=vac.id,
            )
            vac.overlap_with = [o.id for o in peer_overlaps]
            if peer_overlaps and VacationAttentionCode.OVERLAP.value not in vac.attention_codes:
                vac.attention_codes = self._unique_codes(
                    [*vac.attention_codes, VacationAttentionCode.OVERLAP.value]
                )
                if not needs_attention:
                    # Overlap alone is a warning — keep pending unless hard blocks exist.
                    vac.review_status = VacationReviewStatus.PENDING_APPROVAL.value
        saved, created = await self._vacations.create_inbound(vac)
        if not created:
            summary = "Duplicate provider message; existing vacation returned."
            return {
                "outcome": "DUPLICATE",
                "durable": True,
                "vacation_request_id": str(saved.id),
                "attention_codes": [],
                "summary_code": "DUPLICATE_PROVIDER_MESSAGE",
                "summary": summary,
                "notification": build_notification_instructions(
                    settings=settings,
                    outcome="DUPLICATE",
                    durable=True,
                    attention_codes=[],
                    summary=summary,
                ),
                "prefs_echo": {
                    "notify_on_new_vacation": settings.notify_on_new_vacation,
                    "notify_on_error_or_attention": settings.notify_on_error_or_attention,
                },
            }
        await self._refresh_overlap_peers(
            organization_id,
            employee_id=saved.employee_id,
            exclude_id=saved.id,
            previous_peer_ids=list(saved.overlap_with or []),
        )
        await self._audit.append(
            AuditLogEntry(
                action="vacation.ingested",
                resource_type="vacation_request",
                resource_id=saved.id,
                organization_id=organization_id,
                details={
                    "provider": provider,
                    "provider_message_id": message_id,
                    "status": vac.review_status,
                    "attention_codes": list(vac.attention_codes or []),
                },
            )
        )

        outcome = (
            "REQUIRES_ATTENTION"
            if vac.review_status == VacationReviewStatus.REQUIRES_ATTENTION.value
            else "SUCCESS"
        )
        summary = (
            f"Vacation request stored ({outcome}). "
            f"Employee email={email or 'missing'}; "
            f"dates={start}..{end}; codes={','.join(vac.attention_codes) or 'none'}."
        )
        if VacationAttentionCode.EMPLOYEE_NOT_FOUND.value in vac.attention_codes:
            summary = (
                f"Vacation request was received but no employee with email {email} "
                "exists in Payroll Copilot. Manual review is required. STORED BUT NEEDS ATTENTION."
            )
        return {
            "outcome": outcome,
            "durable": True,
            "vacation_request_id": str(saved.id),
            "attention_codes": list(vac.attention_codes or []),
            "summary_code": (vac.attention_codes[0] if vac.attention_codes else outcome),
            "summary": summary,
            "notification": build_notification_instructions(
                settings=settings,
                outcome=outcome,
                durable=True,
                attention_codes=list(vac.attention_codes or []),
                summary=summary,
            ),
            "prefs_echo": {
                "notify_on_new_vacation": settings.notify_on_new_vacation,
                "notify_on_error_or_attention": settings.notify_on_error_or_attention,
            },
        }

    # ---- pipeline events ------------------------------------------------

    async def record_pipeline_event(
        self,
        organization_id: UUID,
        *,
        event_id: str,
        event_type: str,
        occurred_at: datetime | None = None,
        provider: str | None = None,
        provider_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del occurred_at, provider, provider_message_id, metadata
        try:
            VacationPipelineEventType(event_type)
        except ValueError as exc:
            raise ValueError("invalid_event_type") from exc
        if not event_id or len(event_id) > 128:
            raise ValueError("invalid_event_id")
        ttl = int((_now() + timedelta(days=14)).timestamp())
        claimed = await self._pipeline.try_claim_event(
            organization_id, event_id=event_id, ttl_epoch=ttl
        )
        if not claimed:
            return {"status": "duplicate", "event_id": event_id}
        day = _now().date().isoformat()
        await self._pipeline.increment(
            organization_id, day=day, event_type=event_type, amount=1
        )
        return {"status": "recorded", "event_id": event_id, "day": day}

    async def pipeline_analytics(self, organization_id: UUID, *, year: int) -> dict[str, Any]:
        counters = await self._pipeline.get_counters(organization_id, year=year)
        totals: dict[str, int] = {}
        for day_counts in counters.values():
            for key, value in day_counts.items():
                totals[key] = totals.get(key, 0) + int(value)
        return {"year": year, "by_day": counters, "totals": totals}


class ReconcileEmployeeLeaveStatusUseCase:
    """Set on_leave from approved vacations covering today; preserve manual on_leave."""

    def __init__(
        self,
        *,
        vacations: VacationRequestRepository,
        employees: EmployeeRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._vacations = vacations
        self._employees = employees
        self._audit = audit

    async def execute(self, organization_id: UUID) -> dict[str, Any]:
        from payroll_copilot.application.ports.employee_audit import EmployeeListFilter

        today = _now().date()
        employees = await self._employees.list(
            EmployeeListFilter(organization_id=organization_id, include_disabled=True, limit=500)
        )
        flipped = 0
        for emp in employees:
            if emp.status in {EmployeeStatus.TERMINATED, EmployeeStatus.DISABLED}:
                continue
            emp_vacations = await self._vacations.list_for_employee(organization_id, emp.id)
            # Only NEW (or blank/manual) approved vacations drive leave status.
            # Approved update/cancel proposals preserve history but must not
            # double-count leave windows.
            covering = [
                v
                for v in emp_vacations
                if v.review_status == VacationReviewStatus.APPROVED.value
                and (v.intent or VacationIntent.NEW.value)
                in {VacationIntent.NEW.value, "", "manual"}
                and v.start_date
                and v.end_date
                and v.start_date <= today <= v.end_date
            ]
            meta = dict(emp.metadata or {})
            source = str(meta.get("leave_status_source") or LeaveStatusSource.UNKNOWN.value)

            if covering:
                if emp.status != EmployeeStatus.ON_LEAVE:
                    emp.status = EmployeeStatus.ON_LEAVE
                    meta["leave_status_source"] = LeaveStatusSource.VACATION_SYSTEM.value
                    emp.metadata = meta
                    await self._employees.save(emp)
                    flipped += 1
                    await self._audit.append(
                        AuditLogEntry(
                            action="employee.status_reconciled",
                            resource_type="employee",
                            resource_id=emp.id,
                            organization_id=organization_id,
                            details={"status": "on_leave", "source": "vacation_system"},
                        )
                    )
                elif source != LeaveStatusSource.MANUAL.value:
                    meta["leave_status_source"] = LeaveStatusSource.VACATION_SYSTEM.value
                    emp.metadata = meta
                    await self._employees.save(emp)
            else:
                if (
                    emp.status == EmployeeStatus.ON_LEAVE
                    and source == LeaveStatusSource.VACATION_SYSTEM.value
                ):
                    emp.status = EmployeeStatus.ACTIVE
                    meta["leave_status_source"] = LeaveStatusSource.UNKNOWN.value
                    emp.metadata = meta
                    await self._employees.save(emp)
                    flipped += 1
                    await self._audit.append(
                        AuditLogEntry(
                            action="employee.status_reconciled",
                            resource_type="employee",
                            resource_id=emp.id,
                            organization_id=organization_id,
                            details={"status": "active", "source": "vacation_system"},
                        )
                    )
        return {"organization_id": str(organization_id), "updated": flipped}
