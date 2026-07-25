"""Accountant vacation management routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.use_cases.manage_vacations import ManageVacationsUseCase
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.infrastructure.email.factory import create_email_service
from payroll_copilot.presentation.api.security import AuthPrincipal, require_accountant
from payroll_copilot.infrastructure.security.rate_limiter import get_rate_limiter
from payroll_copilot.infrastructure.config.settings import get_settings

router = APIRouter()


def _use_case() -> ManageVacationsUseCase:
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    settings = get_settings()
    return ManageVacationsUseCase(
        vacations=dynamo_persistence.get_vacation_request_repository(),
        settings_repo=dynamo_persistence.get_vacation_settings_repository(),
        otp_repo=dynamo_persistence.get_email_ownership_otp_repository(),
        pipeline=dynamo_persistence.get_vacation_pipeline_analytics_repository(),
        employees=dynamo_persistence.get_employee_repository(),
        audit=dynamo_persistence.get_audit_log_repository(),
        email=create_email_service(settings),
        object_storage=create_object_storage(settings),
        credentials=dynamo_persistence.get_integration_credential_repository(),
    )


def _org(principal: AuthPrincipal) -> UUID:
    if principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "org_required", "message": "Organization binding required."},
        )
    return principal.organization_id


def _serialize_vacation(v: Any) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "organization_id": str(v.organization_id),
        "employee_id": str(v.employee_id) if v.employee_id else None,
        "extracted_employee_email": v.extracted_employee_email,
        "extracted_employee_name": v.extracted_employee_name,
        "sender_email": v.sender_email,
        "start_date": v.start_date.isoformat() if v.start_date else None,
        "end_date": v.end_date.isoformat() if v.end_date else None,
        "provider": v.provider,
        "provider_message_id": v.provider_message_id,
        "provider_thread_id": v.provider_thread_id,
        "original_subject": v.original_subject,
        "original_body_text": v.original_body_text,
        "original_body_s3_key": v.original_body_s3_key,
        "received_at": v.received_at.isoformat() if v.received_at else None,
        "ai_confidence": v.ai_confidence,
        "ai_explanation": v.ai_explanation,
        "ai_extraction_original": dict(v.ai_extraction_original)
        if isinstance(getattr(v, "ai_extraction_original", None), dict)
        else None,
        "intent": v.intent,
        "related_vacation_id": str(v.related_vacation_id) if v.related_vacation_id else None,
        "source": v.source,
        "review_status": v.review_status,
        "attention_codes": list(v.attention_codes or []),
        "attention_detail": v.attention_detail,
        "overlap_with": [str(x) for x in (getattr(v, "overlap_with", None) or [])],
        "seen_at": v.seen_at.isoformat() if v.seen_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        "created_by": str(v.created_by) if v.created_by else None,
        "approved_by": str(v.approved_by) if v.approved_by else None,
        "approved_at": v.approved_at.isoformat() if v.approved_at else None,
    }


async def _serialize_settings(s: Any, *, email_automation_status: str) -> dict[str, Any]:
    app = get_settings()
    return {
        "monitored_email_verified": s.monitored_email_verified,  # legacy; not used by V1 UI
        "monitored_email_pending": s.monitored_email_pending,  # legacy; not used by V1 UI
        "notification_email_verified": s.notification_email_verified,
        "notification_email_pending": s.notification_email_pending,
        "notify_on_new_vacation": s.notify_on_new_vacation,
        "notify_on_error_or_attention": s.notify_on_error_or_attention,
        "notify_on_new_sick_leave": s.notify_on_new_sick_leave,
        "notify_on_sick_leave_error_or_attention": s.notify_on_sick_leave_error_or_attention,
        "active_monitored_email": s.active_monitored_email,
        "mailbox_connection_status": s.mailbox_connection_status,
        "mailbox_last_check_at": s.mailbox_last_check_at.isoformat()
        if s.mailbox_last_check_at
        else None,
        "mailbox_last_processed_at": s.mailbox_last_processed_at.isoformat()
        if s.mailbox_last_processed_at
        else None,
        "mailbox_last_processed_message_id": s.mailbox_last_processed_message_id,
        "mailbox_last_error_code": s.mailbox_last_error_code,
        "mailbox_last_error_message": s.mailbox_last_error_message,
        "email_automation_status": email_automation_status,
        "support_contact": {
            "name": (app.support_contact_name or "").strip() or None,
            "email": (app.support_contact_email or "").strip() or None,
            "phone": (app.support_contact_phone or "").strip() or None,
        },
    }


async def _settings_response(organization_id: UUID) -> dict[str, Any]:
    uc = _use_case()
    settings = await uc.get_settings(organization_id)
    status = await uc.email_automation_status(organization_id)
    return await _serialize_settings(settings, email_automation_status=status)


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notify_on_new_vacation: bool | None = None
    notify_on_error_or_attention: bool | None = None
    notify_on_new_sick_leave: bool | None = None
    notify_on_sick_leave_error_or_attention: bool | None = None
    # Present in payload (including null/empty) means update destination without OTP.
    notification_email: str | None = None


class StartVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)


class ConfirmVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=4, max_length=12)


class ManualVacationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: UUID | None = None
    employee_email: str | None = None
    employee_name: str | None = None
    start_date: date
    end_date: date
    subject: str | None = None
    notes: str | None = None


class VacationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date | None = None
    end_date: date | None = None
    extracted_employee_email: str | None = None
    extracted_employee_name: str | None = None
    employee_id: UUID | None = None
    attention_detail: str | None = None


class LinkEmployeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: UUID


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_warnings: bool = False


class BulkApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vacation_ids: list[UUID] = Field(min_length=1, max_length=100)
    confirm_warnings: bool = False


class BulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vacation_ids: list[UUID] = Field(min_length=1, max_length=100)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None


class MarkSeenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vacation_ids: list[UUID] | None = None
    seen_before: datetime | None = None


@router.get("/settings")
async def get_vacation_settings(
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return await _settings_response(_org(principal))


@router.patch("/settings/preferences")
async def patch_vacation_preferences(
    body: PreferencesPatch,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    try:
        await _use_case().patch_preferences(
            _org(principal),
            actor_user_id=principal.user_id,
            notify_on_new_vacation=fields.get("notify_on_new_vacation"),
            notify_on_error_or_attention=fields.get("notify_on_error_or_attention"),
            notify_on_new_sick_leave=fields.get("notify_on_new_sick_leave"),
            notify_on_sick_leave_error_or_attention=fields.get(
                "notify_on_sick_leave_error_or_attention"
            ),
            notification_email=fields.get("notification_email"),
            update_notification_email="notification_email" in fields,
        )
    except ValueError as exc:
        if str(exc) == "invalid_email":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_email", "message": "Invalid email format."},
            ) from exc
        raise
    return await _settings_response(_org(principal))


async def _start_verify(purpose: str, body: StartVerificationRequest, principal: AuthPrincipal):
    settings = get_settings()
    get_rate_limiter().enforce(
        f"vacation_otp_{purpose}",
        f"{_org(principal)}:{body.email.strip().lower()}",
        getattr(settings, "rate_limit_vacation_otp_per_hour", 10),
        3600,
    )
    try:
        return await _use_case().start_email_verification(
            _org(principal),
            purpose=purpose,
            email=body.email,
            actor_user_id=principal.user_id,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "monitored_otp_retired":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "monitored_otp_retired",
                    "message": "Monitored mailbox is administrator-managed in V1.",
                },
            ) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


async def _confirm_verify(purpose: str, body: ConfirmVerificationRequest, principal: AuthPrincipal):
    try:
        await _use_case().confirm_email_verification(
            _org(principal),
            purpose=purpose,
            email=body.email,
            code=body.code,
            actor_user_id=principal.user_id,
        )
        return await _settings_response(_org(principal))
    except ValueError as exc:
        code = str(exc)
        if code == "monitored_otp_retired":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "monitored_otp_retired",
                    "message": "Monitored mailbox is administrator-managed in V1.",
                },
            ) from exc
        status_code = status.HTTP_400_BAD_REQUEST
        if code == "otp_expired":
            status_code = status.HTTP_410_GONE
        raise HTTPException(status_code=status_code, detail={"code": code}) from exc


@router.post("/settings/monitored-email/start-verification")
async def start_monitored_verification(
    body: StartVerificationRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    """Retired in V1 — monitored mailbox is provisioned by administrators."""
    del body, principal
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "monitored_otp_retired",
            "message": "Monitored mailbox is administrator-managed in V1.",
        },
    )


@router.post("/settings/monitored-email/confirm-verification")
async def confirm_monitored_verification(
    body: ConfirmVerificationRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    """Retired in V1 — monitored mailbox is provisioned by administrators."""
    del body, principal
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "monitored_otp_retired",
            "message": "Monitored mailbox is administrator-managed in V1.",
        },
    )


@router.post("/settings/notification-email/start-verification")
async def start_notification_verification(
    body: StartVerificationRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return await _start_verify("notification", body, principal)


@router.post("/settings/notification-email/confirm-verification")
async def confirm_notification_verification(
    body: ConfirmVerificationRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return await _confirm_verify("notification", body, principal)


@router.get("")
async def list_vacations(
    principal: AuthPrincipal = Depends(require_accountant),
    bucket: str | None = Query(default="active"),
    range_start: date | None = Query(default=None),
    range_end: date | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = await _use_case().list_vacations(
        _org(principal),
        bucket=bucket,
        range_start=range_start,
        range_end=range_end,
        query=query,
        limit=limit,
        offset=offset,
    )
    return {"items": [_serialize_vacation(v) for v in rows]}


@router.get("/unseen-count")
async def unseen_count(
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return {"count": await _use_case().unseen_count(_org(principal))}


@router.post("/mark-seen")
async def mark_seen(
    body: MarkSeenRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    updated = await _use_case().mark_seen(
        _org(principal),
        vacation_ids=body.vacation_ids,
        seen_before=body.seen_before,
    )
    return {"updated": updated}


@router.post("/bulk-approve")
async def bulk_approve(
    body: BulkApproveRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return await _use_case().bulk_approve(
        _org(principal),
        body.vacation_ids,
        actor_user_id=principal.user_id,
        confirm_warnings=body.confirm_warnings,
    )


@router.post("/bulk-delete")
async def bulk_delete(
    body: BulkDeleteRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    return await _use_case().bulk_delete(
        _org(principal),
        body.vacation_ids,
        actor_user_id=principal.user_id,
    )


@router.post("/integration-credentials", status_code=status.HTTP_403_FORBIDDEN)
async def create_integration_credential_retired(
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    """Retired for accountants in V1 — use developer-admin credential APIs."""
    del principal
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "admin_provisioning_required",
            "message": (
                "Organization n8n API keys are created by a system administrator."
            ),
        },
    )


@router.get("/{vacation_id}")
async def get_vacation(
    vacation_id: UUID,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    vac = await _use_case().get_vacation(_org(principal), vacation_id)
    if vac is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _serialize_vacation(vac)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_manual_vacation(
    body: ManualVacationCreate,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    vac = await _use_case().create_manual(
        _org(principal),
        actor_user_id=principal.user_id,
        employee_id=body.employee_id,
        employee_email=body.employee_email,
        employee_name=body.employee_name,
        start_date=body.start_date,
        end_date=body.end_date,
        subject=body.subject,
        notes=body.notes,
    )
    return _serialize_vacation(vac)


@router.patch("/{vacation_id}")
async def update_vacation(
    vacation_id: UUID,
    body: VacationUpdateRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        vac = await _use_case().update_vacation(
            _org(principal),
            vacation_id,
            actor_user_id=principal.user_id,
            **body.model_dump(exclude_unset=True),
        )
        return _serialize_vacation(vac)
    except ValueError as exc:
        detail = str(exc)
        if detail == "employee_not_found":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": detail, "message": "Employee not found in organization."},
            ) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc


@router.delete("/{vacation_id}")
async def delete_vacation(
    vacation_id: UUID,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        result = await _use_case().cancel_or_delete(
            _org(principal), vacation_id, actor_user_id=principal.user_id
        )
        if result is None:
            return {"status": "deleted"}
        return _serialize_vacation(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{vacation_id}/link-employee")
async def link_employee(
    vacation_id: UUID,
    body: LinkEmployeeRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        vac = await _use_case().link_employee(
            _org(principal),
            vacation_id,
            employee_id=body.employee_id,
            actor_user_id=principal.user_id,
        )
        return _serialize_vacation(vac)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{vacation_id}/approve")
async def approve_vacation(
    vacation_id: UUID,
    body: ApproveRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        vac = await _use_case().approve(
            _org(principal),
            vacation_id,
            actor_user_id=principal.user_id,
            confirm_warnings=body.confirm_warnings,
        )
        return _serialize_vacation(vac)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("confirmation_required:"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "confirmation_required",
                    "codes": msg.split(":", 1)[1].split(","),
                },
            ) from exc
        if msg.startswith("blocked:"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "blocked", "codes": msg.split(":", 1)[1].split(",")},
            ) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc


@router.post("/{vacation_id}/reject")
async def reject_vacation(
    vacation_id: UUID,
    body: RejectRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        vac = await _use_case().reject(
            _org(principal),
            vacation_id,
            actor_user_id=principal.user_id,
            reason=body.reason,
        )
        return _serialize_vacation(vac)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
