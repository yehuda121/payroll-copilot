"""Accountant sick-leave management routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.use_cases.manage_sick_leaves import ManageSickLeavesUseCase
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.presentation.api.security import AuthPrincipal, require_accountant

router = APIRouter()


def _use_case() -> ManageSickLeavesUseCase:
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    settings = get_settings()
    return ManageSickLeavesUseCase(
        sick_leaves=dynamo_persistence.get_sick_leave_request_repository(),
        settings_repo=dynamo_persistence.get_vacation_settings_repository(),
        employees=dynamo_persistence.get_employee_repository(),
        audit=dynamo_persistence.get_audit_log_repository(),
        object_storage=create_object_storage(settings),
    )


def _org(principal: AuthPrincipal) -> UUID:
    if principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "org_required", "message": "Organization binding required."},
        )
    return principal.organization_id


def _serialize_sick_leave(v: Any) -> dict[str, Any]:
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
        "related_sick_leave_id": str(v.related_sick_leave_id) if v.related_sick_leave_id else None,
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


class ManualSickLeaveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: UUID | None = None
    employee_email: str | None = None
    employee_name: str | None = None
    start_date: date
    end_date: date
    subject: str | None = None
    notes: str | None = None


class SickLeaveUpdateRequest(BaseModel):
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
    sick_leave_ids: list[UUID] = Field(min_length=1, max_length=100)
    confirm_warnings: bool = False


class BulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sick_leave_ids: list[UUID] = Field(min_length=1, max_length=100)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None


class MarkSeenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sick_leave_ids: list[UUID] | None = None
    seen_before: datetime | None = None


@router.get("")
async def list_sick_leaves(
    principal: AuthPrincipal = Depends(require_accountant),
    bucket: str | None = Query(default="active"),
    range_start: date | None = Query(default=None),
    range_end: date | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = await _use_case().list_sick_leaves(
        _org(principal),
        bucket=bucket,
        range_start=range_start,
        range_end=range_end,
        query=query,
        limit=limit,
        offset=offset,
    )
    return {"items": [_serialize_sick_leave(v) for v in rows]}


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
        sick_leave_ids=body.sick_leave_ids,
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
        body.sick_leave_ids,
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
        body.sick_leave_ids,
        actor_user_id=principal.user_id,
    )


@router.get("/{sick_leave_id}")
async def get_sick_leave(
    sick_leave_id: UUID,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    row = await _use_case().get_sick_leave(_org(principal), sick_leave_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _serialize_sick_leave(row)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_manual_sick_leave(
    body: ManualSickLeaveCreate,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    row = await _use_case().create_manual(
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
    return _serialize_sick_leave(row)


@router.patch("/{sick_leave_id}")
async def update_sick_leave(
    sick_leave_id: UUID,
    body: SickLeaveUpdateRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        row = await _use_case().update_sick_leave(
            _org(principal),
            sick_leave_id,
            actor_user_id=principal.user_id,
            **body.model_dump(exclude_unset=True),
        )
        return _serialize_sick_leave(row)
    except ValueError as exc:
        detail = str(exc)
        if detail == "employee_not_found":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": detail, "message": "Employee not found in organization."},
            ) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc


@router.delete("/{sick_leave_id}")
async def delete_sick_leave(
    sick_leave_id: UUID,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        result = await _use_case().cancel_or_delete(
            _org(principal), sick_leave_id, actor_user_id=principal.user_id
        )
        if result is None:
            return {"status": "deleted"}
        return _serialize_sick_leave(result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{sick_leave_id}/link-employee")
async def link_employee(
    sick_leave_id: UUID,
    body: LinkEmployeeRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        row = await _use_case().link_employee(
            _org(principal),
            sick_leave_id,
            employee_id=body.employee_id,
            actor_user_id=principal.user_id,
        )
        return _serialize_sick_leave(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{sick_leave_id}/approve")
async def approve_sick_leave(
    sick_leave_id: UUID,
    body: ApproveRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        row = await _use_case().approve(
            _org(principal),
            sick_leave_id,
            actor_user_id=principal.user_id,
            confirm_warnings=body.confirm_warnings,
        )
        return _serialize_sick_leave(row)
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


@router.post("/{sick_leave_id}/reject")
async def reject_sick_leave(
    sick_leave_id: UUID,
    body: RejectRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        row = await _use_case().reject(
            _org(principal),
            sick_leave_id,
            actor_user_id=principal.user_id,
            reason=body.reason,
        )
        return _serialize_sick_leave(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
