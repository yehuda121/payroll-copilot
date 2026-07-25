"""Sick leave management use cases — SoT mutations and email ingest."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository, EmployeeRepository
from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.sick_leave_requests import (
    SickLeaveListFilter,
    SickLeaveRequestRepository,
)
from payroll_copilot.application.ports.vacation_settings import VacationSettingsRepository
from payroll_copilot.application.services.sick_leave_rules import (
    HARD_BLOCK_CODES,
    LOW_CONFIDENCE_THRESHOLD,
    MAX_BODY_INLINE_CHARS,
    WARNING_CODES,
    ApprovalClassification,
    build_notification_instructions,
    classify_sick_leave_for_approval,
    collect_date_attention_codes,
    find_sick_leave_duplicate_content,
    find_sick_leave_overlaps,
    match_employee_by_email,
    normalize_email,
    resolve_related_sick_leave,
)
from payroll_copilot.domain.entities import SickLeaveRequest
from payroll_copilot.domain.enums import (
    SickLeaveAttentionCode,
    SickLeaveIntent,
    SickLeaveReviewStatus,
    SickLeaveSource,
)

logger = logging.getLogger(__name__)


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

def _now() -> datetime:
    return datetime.now(UTC)

def _parse_date(value: str | date | None) -> date | None:
    if value is None or value == '':
        return None
    if isinstance(value, date) and (not isinstance(value, datetime)):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

@dataclass
class InboundSickLeaveCommand:
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

class ManageSickLeavesUseCase:

    def __init__(self, *, sick_leaves: SickLeaveRequestRepository, settings_repo: VacationSettingsRepository, employees: EmployeeRepository, audit: AuditLogRepository, object_storage: ObjectStoragePort | None=None) -> None:
        self._sick_leaves = sick_leaves
        self._settings = settings_repo
        self._employees = employees
        self._audit = audit
        self._object_storage = object_storage

    def _enqueue_leave_reconcile(self, organization_id: UUID) -> None:
        try:
            from payroll_copilot.infrastructure.tasks.celery_app import reconcile_employee_leave_status
            reconcile_employee_leave_status.delay(str(organization_id))
        except Exception:
            logger.debug('Could not enqueue leave reconciliation for org %s', organization_id, exc_info=True)

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
        if hard or intent in {SickLeaveIntent.UPDATE.value, SickLeaveIntent.CANCEL.value, SickLeaveIntent.UNKNOWN.value}:
            return SickLeaveReviewStatus.REQUIRES_ATTENTION.value
        return SickLeaveReviewStatus.PENDING_APPROVAL.value

    @staticmethod
    def _snapshot_ai_extraction(*, employee_email: str | None, employee_name: str | None, start_date: date | None, end_date: date | None, confidence: float | None, explanation: str | None) -> dict[str, Any]:
        return {'employee_email': employee_email, 'employee_name': employee_name, 'start_date': start_date.isoformat() if start_date else None, 'end_date': end_date.isoformat() if end_date else None, 'confidence': confidence, 'explanation': (explanation or '')[:2000] or None}

    async def revalidate_sick_leave(self, vac: SickLeaveRequest, *, rematch_employee: bool=False, explicit_employee_id: UUID | None=None, explicit_employee_id_set: bool=False) -> SickLeaveRequest:
        """Recompute match, dates, duplicate/overlap codes, status, and peer overlaps."""
        org_id = vac.organization_id
        if explicit_employee_id_set:
            if explicit_employee_id is None:
                vac.employee_id = None
            else:
                emp = await self._employees.get_by_id(explicit_employee_id)
                if emp is None or emp.organization_id != org_id:
                    raise ValueError('employee_not_found')
                vac.employee_id = explicit_employee_id
        elif rematch_employee:
            match = await match_employee_by_email(self._employees, org_id, vac.extracted_employee_email)
            vac.employee_id = match.employee.id if match.employee else None
        volatile = HARD_BLOCK_CODES | WARNING_CODES | {SickLeaveAttentionCode.DUPLICATE_CONTENT.value, SickLeaveAttentionCode.LOW_CONFIDENCE.value, SickLeaveAttentionCode.OVERLAP.value}
        preserved = [c for c in vac.attention_codes or [] if c not in volatile]
        codes = list(preserved)
        if not vac.extracted_employee_email:
            codes.append(SickLeaveAttentionCode.MISSING_EMPLOYEE_EMAIL.value)
        elif vac.employee_id is None:
            match = await match_employee_by_email(self._employees, org_id, vac.extracted_employee_email)
            if match.code:
                codes.append(match.code)
            vac.employee_id = match.employee.id if match.employee else None
        codes.extend(collect_date_attention_codes(vac.start_date, vac.end_date))
        if vac.ai_confidence is not None and vac.ai_confidence < LOW_CONFIDENCE_THRESHOLD and (vac.source == SickLeaveSource.EMAIL.value):
            codes.append(SickLeaveAttentionCode.LOW_CONFIDENCE.value)
        if vac.intent in {SickLeaveIntent.UPDATE.value, SickLeaveIntent.CANCEL.value}:
            if vac.related_sick_leave_id is None:
                codes.append(SickLeaveAttentionCode.AMBIGUOUS_UPDATE.value if vac.intent == SickLeaveIntent.UPDATE.value else SickLeaveAttentionCode.AMBIGUOUS_CANCEL.value)
            else:
                codes.append(SickLeaveAttentionCode.UPDATE_PROPOSED.value if vac.intent == SickLeaveIntent.UPDATE.value else SickLeaveAttentionCode.CANCEL_PROPOSED.value)
        overlaps: list[SickLeaveRequest] = []
        if vac.employee_id and vac.start_date and vac.end_date:
            dup = await find_sick_leave_duplicate_content(self._sick_leaves, org_id, employee_id=vac.employee_id, start_date=vac.start_date, end_date=vac.end_date, exclude_id=vac.id)
            if dup:
                codes.append(SickLeaveAttentionCode.DUPLICATE_CONTENT.value)
            overlaps = await find_sick_leave_overlaps(self._sick_leaves, org_id, employee_id=vac.employee_id, start_date=vac.start_date, end_date=vac.end_date, exclude_id=vac.id)
            if overlaps:
                codes.append(SickLeaveAttentionCode.OVERLAP.value)
        vac.attention_codes = self._unique_codes(codes)
        vac.overlap_with = [o.id for o in overlaps]
        if vac.review_status not in {SickLeaveReviewStatus.APPROVED.value, SickLeaveReviewStatus.REJECTED.value, SickLeaveReviewStatus.CANCELLED.value}:
            vac.review_status = self._review_status_from_codes(vac.attention_codes, intent=vac.intent)
        return vac

    async def _refresh_overlap_peers(self, organization_id: UUID, *, employee_id: UUID | None, exclude_id: UUID | None=None, previous_peer_ids: list[UUID] | None=None) -> None:
        """Recompute OVERLAP on peers that may have changed due to this write."""
        peer_ids: set[UUID] = set(previous_peer_ids or [])
        if employee_id is not None:
            for peer in await self._sick_leaves.list_for_employee(organization_id, employee_id):
                peer_ids.add(peer.id)
        for peer_id in peer_ids:
            if exclude_id and peer_id == exclude_id:
                continue
            peer = await self._sick_leaves.get_by_id(organization_id, peer_id)
            if peer is None:
                continue
            if peer.review_status in {SickLeaveReviewStatus.REJECTED.value, SickLeaveReviewStatus.CANCELLED.value}:
                continue
            await self.revalidate_sick_leave(peer, rematch_employee=False)
            await self._sick_leaves.save(peer)

    async def list_sick_leaves(self, organization_id: UUID, **kwargs: Any) -> list[SickLeaveRequest]:
        return await self._sick_leaves.list(SickLeaveListFilter(organization_id=organization_id, **kwargs))

    async def get_sick_leave(self, organization_id: UUID, sick_leave_id: UUID) -> SickLeaveRequest | None:
        return await self._sick_leaves.get_by_id(organization_id, sick_leave_id)

    async def create_manual(self, organization_id: UUID, *, actor_user_id: UUID | None, employee_id: UUID | None, employee_email: str | None, employee_name: str | None, start_date: date, end_date: date, subject: str | None=None, notes: str | None=None) -> SickLeaveRequest:
        codes = collect_date_attention_codes(start_date, end_date)
        match = await match_employee_by_email(self._employees, organization_id, employee_email)
        linked = employee_id or (match.employee.id if match.employee else None)
        if employee_id is None and match.code:
            codes.append(match.code)
        if linked:
            overlaps = await find_sick_leave_overlaps(self._sick_leaves, organization_id, employee_id=linked, start_date=start_date, end_date=end_date)
            if overlaps:
                codes.append(SickLeaveAttentionCode.OVERLAP.value)
        status = SickLeaveReviewStatus.REQUIRES_ATTENTION.value if any((c in codes for c in (SickLeaveAttentionCode.EMPLOYEE_NOT_FOUND.value, SickLeaveAttentionCode.EMPLOYEE_AMBIGUOUS.value, SickLeaveAttentionCode.END_BEFORE_START.value, SickLeaveAttentionCode.MISSING_START_DATE.value, SickLeaveAttentionCode.MISSING_END_DATE.value))) else SickLeaveReviewStatus.PENDING_APPROVAL.value
        vac = SickLeaveRequest(id=uuid4(), organization_id=organization_id, employee_id=linked, extracted_employee_email=normalize_email(employee_email), extracted_employee_name=employee_name, start_date=start_date, end_date=end_date, source=SickLeaveSource.MANUAL.value, intent=SickLeaveIntent.NEW.value, review_status=status, attention_codes=codes, attention_detail=notes, original_subject=subject or 'Manual sick leave', original_body_text=notes, ai_confidence=1.0, created_by=actor_user_id, created_at=_now(), updated_at=_now())
        saved = await self._sick_leaves.save(vac)
        await self._audit.append(AuditLogEntry(action='sick_leave.created_manual', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id, details={'start_date': str(start_date), 'end_date': str(end_date)}))
        return saved

    async def update_sick_leave(self, organization_id: UUID, sick_leave_id: UUID, *, actor_user_id: UUID | None, **fields: Any) -> SickLeaveRequest:
        vac = await self._sick_leaves.get_by_id(organization_id, sick_leave_id)
        if vac is None:
            raise ValueError('not_found')
        before = {'extracted_employee_email': vac.extracted_employee_email, 'extracted_employee_name': vac.extracted_employee_name, 'start_date': vac.start_date.isoformat() if vac.start_date else None, 'end_date': vac.end_date.isoformat() if vac.end_date else None, 'employee_id': str(vac.employee_id) if vac.employee_id else None, 'review_status': vac.review_status, 'attention_codes': list(vac.attention_codes or [])}
        previous_peers = list(vac.overlap_with or [])
        previous_employee_id = vac.employee_id
        rematch = False
        explicit_set = False
        explicit_id: UUID | None = None
        if 'start_date' in fields:
            vac.start_date = fields['start_date']
        if 'end_date' in fields:
            vac.end_date = fields['end_date']
        if 'extracted_employee_email' in fields:
            vac.extracted_employee_email = normalize_email(fields['extracted_employee_email'])
            rematch = True
        if 'extracted_employee_name' in fields:
            vac.extracted_employee_name = fields['extracted_employee_name']
        if 'employee_id' in fields:
            explicit_set = True
            explicit_id = fields['employee_id']
        if 'attention_detail' in fields:
            vac.attention_detail = fields['attention_detail']
        await self.revalidate_sick_leave(vac, rematch_employee=rematch and (not explicit_set), explicit_employee_id=explicit_id, explicit_employee_id_set=explicit_set)
        saved = await self._sick_leaves.save(vac)
        await self._refresh_overlap_peers(organization_id, employee_id=saved.employee_id or previous_employee_id, exclude_id=saved.id, previous_peer_ids=previous_peers)
        after = {'extracted_employee_email': saved.extracted_employee_email, 'extracted_employee_name': saved.extracted_employee_name, 'start_date': saved.start_date.isoformat() if saved.start_date else None, 'end_date': saved.end_date.isoformat() if saved.end_date else None, 'employee_id': str(saved.employee_id) if saved.employee_id else None, 'review_status': saved.review_status, 'attention_codes': list(saved.attention_codes or [])}
        await self._audit.append(AuditLogEntry(action='sick_leave.updated', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id, details={'fields': list(fields.keys()), 'before': before, 'after': after}))
        return saved

    async def cancel_or_delete(self, organization_id: UUID, sick_leave_id: UUID, *, actor_user_id: UUID | None) -> SickLeaveRequest | None:
        vac = await self._sick_leaves.get_by_id(organization_id, sick_leave_id)
        if vac is None:
            raise ValueError('not_found')
        previous_peers = list(vac.overlap_with or [])
        previous_employee_id = vac.employee_id
        if vac.review_status == SickLeaveReviewStatus.APPROVED.value:
            vac.review_status = SickLeaveReviewStatus.CANCELLED.value
            vac.attention_codes = [c for c in vac.attention_codes or [] if c != SickLeaveAttentionCode.OVERLAP.value]
            vac.overlap_with = []
            saved = await self._sick_leaves.save(vac)
            await self._audit.append(AuditLogEntry(action='sick_leave.cancelled', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id))
            await self._refresh_overlap_peers(organization_id, employee_id=previous_employee_id, exclude_id=saved.id, previous_peer_ids=previous_peers)
            self._enqueue_leave_reconcile(organization_id)
            return saved
        await self._sick_leaves.delete(organization_id, sick_leave_id)
        await self._audit.append(AuditLogEntry(action='sick_leave.deleted', resource_type='sick_leave_request', resource_id=sick_leave_id, organization_id=organization_id, user_id=actor_user_id))
        await self._refresh_overlap_peers(organization_id, employee_id=previous_employee_id, exclude_id=sick_leave_id, previous_peer_ids=previous_peers)
        self._enqueue_leave_reconcile(organization_id)
        return None

    async def bulk_delete(self, organization_id: UUID, sick_leave_ids: list[UUID], *, actor_user_id: UUID | None) -> dict[str, Any]:
        deleted: list[dict[str, str]] = []
        cancelled: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        for vid in sick_leave_ids:
            try:
                result = await self.cancel_or_delete(organization_id, vid, actor_user_id=actor_user_id)
                if result is None:
                    deleted.append({'id': str(vid)})
                else:
                    cancelled.append({'id': str(vid)})
            except ValueError as exc:
                failed.append({'id': str(vid), 'error': str(exc) or 'failed'})
            except Exception as exc:
                failed.append({'id': str(vid), 'error': type(exc).__name__})
        await self._audit.append(AuditLogEntry(action='sick_leave.bulk_deleted', resource_type='sick_leave_request', organization_id=organization_id, user_id=actor_user_id, details={'deleted': [row['id'] for row in deleted], 'cancelled': [row['id'] for row in cancelled], 'failed': failed}))
        return {'status': 'completed', 'deleted': deleted, 'cancelled': cancelled, 'failed': failed}

    async def link_employee(self, organization_id: UUID, sick_leave_id: UUID, *, employee_id: UUID, actor_user_id: UUID | None) -> SickLeaveRequest:
        vac = await self._sick_leaves.get_by_id(organization_id, sick_leave_id)
        if vac is None:
            raise ValueError('not_found')
        emp = await self._employees.get_by_id(employee_id)
        if emp is None or emp.organization_id != organization_id:
            raise ValueError('employee_not_found')
        vac.employee_id = employee_id
        vac.attention_codes = [c for c in vac.attention_codes if c not in {SickLeaveAttentionCode.EMPLOYEE_NOT_FOUND.value, SickLeaveAttentionCode.EMPLOYEE_AMBIGUOUS.value, SickLeaveAttentionCode.MISSING_EMPLOYEE_EMAIL.value}]
        if not vac.extracted_employee_email:
            vac.extracted_employee_email = normalize_email((emp.metadata or {}).get('email'))
        if vac.review_status == SickLeaveReviewStatus.REQUIRES_ATTENTION.value:
            remaining_hard = [c for c in vac.attention_codes if c in {SickLeaveAttentionCode.MISSING_START_DATE.value, SickLeaveAttentionCode.MISSING_END_DATE.value, SickLeaveAttentionCode.END_BEFORE_START.value, SickLeaveAttentionCode.INVALID_DATE.value, SickLeaveAttentionCode.AMBIGUOUS_UPDATE.value, SickLeaveAttentionCode.AMBIGUOUS_CANCEL.value}]
            if not remaining_hard:
                vac.review_status = SickLeaveReviewStatus.PENDING_APPROVAL.value
        saved = await self._sick_leaves.save(vac)
        await self._audit.append(AuditLogEntry(action='sick_leave.employee_linked', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id, details={'employee_id': str(employee_id)}))
        return saved

    async def classify_approval(self, organization_id: UUID, sick_leave_id: UUID) -> tuple[SickLeaveRequest, ApprovalClassification]:
        vac = await self._sick_leaves.get_by_id(organization_id, sick_leave_id)
        if vac is None:
            raise ValueError('not_found')
        if vac.employee_id and vac.start_date and vac.end_date:
            overlaps = await find_sick_leave_overlaps(self._sick_leaves, organization_id, employee_id=vac.employee_id, start_date=vac.start_date, end_date=vac.end_date, exclude_id=vac.id)
            codes = [c for c in vac.attention_codes if c != SickLeaveAttentionCode.OVERLAP.value]
            if overlaps:
                codes.append(SickLeaveAttentionCode.OVERLAP.value)
            dup = await find_sick_leave_duplicate_content(self._sick_leaves, organization_id, employee_id=vac.employee_id, start_date=vac.start_date, end_date=vac.end_date, exclude_id=vac.id)
            codes = [c for c in codes if c != SickLeaveAttentionCode.DUPLICATE_CONTENT.value]
            if dup:
                codes.append(SickLeaveAttentionCode.DUPLICATE_CONTENT.value)
            vac.attention_codes = codes
        return (vac, classify_sick_leave_for_approval(vac))

    async def approve(self, organization_id: UUID, sick_leave_id: UUID, *, actor_user_id: UUID | None, confirm_warnings: bool=False, apply_update_cancel: bool=True) -> SickLeaveRequest:
        vac, classification = await self.classify_approval(organization_id, sick_leave_id)
        if classification.classification == 'BLOCKED':
            raise ValueError(f"blocked:{','.join(classification.codes)}")
        if classification.classification == 'WARNING' and (not confirm_warnings):
            raise ValueError(f"confirmation_required:{','.join(classification.codes)}")
        if apply_update_cancel and vac.related_sick_leave_id and (vac.intent in {SickLeaveIntent.UPDATE.value, SickLeaveIntent.CANCEL.value}):
            target = await self._sick_leaves.get_by_id(organization_id, vac.related_sick_leave_id)
            if target is not None:
                if vac.intent == SickLeaveIntent.CANCEL.value:
                    target.review_status = SickLeaveReviewStatus.CANCELLED.value
                    await self._sick_leaves.save(target)
                elif vac.intent == SickLeaveIntent.UPDATE.value:
                    if vac.start_date:
                        target.start_date = vac.start_date
                    if vac.end_date:
                        target.end_date = vac.end_date
                    await self._sick_leaves.save(target)
        vac.review_status = SickLeaveReviewStatus.APPROVED.value
        vac.approved_by = actor_user_id
        vac.approved_at = _now()
        vac.attention_codes = [c for c in vac.attention_codes if c not in {SickLeaveAttentionCode.OVERLAP.value, SickLeaveAttentionCode.DUPLICATE_CONTENT.value, SickLeaveAttentionCode.LOW_CONFIDENCE.value, SickLeaveAttentionCode.UPDATE_PROPOSED.value, SickLeaveAttentionCode.CANCEL_PROPOSED.value}]
        saved = await self._sick_leaves.save(vac)
        await self._audit.append(AuditLogEntry(action='sick_leave.approved', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id, details={'confirm_warnings': confirm_warnings}))
        self._enqueue_leave_reconcile(organization_id)
        return saved

    async def reject(self, organization_id: UUID, sick_leave_id: UUID, *, actor_user_id: UUID | None, reason: str | None=None) -> SickLeaveRequest:
        vac = await self._sick_leaves.get_by_id(organization_id, sick_leave_id)
        if vac is None:
            raise ValueError('not_found')
        vac.review_status = SickLeaveReviewStatus.REJECTED.value
        if reason:
            vac.attention_detail = reason
        saved = await self._sick_leaves.save(vac)
        await self._audit.append(AuditLogEntry(action='sick_leave.rejected', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, user_id=actor_user_id))
        return saved

    async def bulk_approve(self, organization_id: UUID, sick_leave_ids: list[UUID], *, actor_user_id: UUID | None, confirm_warnings: bool=False) -> dict[str, Any]:
        preview: list[dict[str, Any]] = []
        for vid in sick_leave_ids:
            try:
                vac, classification = await self.classify_approval(organization_id, vid)
                preview.append({'id': str(vid), 'classification': classification.classification, 'codes': classification.codes, 'detail': classification.detail, 'employee_id': str(vac.employee_id) if vac.employee_id else None})
            except ValueError:
                preview.append({'id': str(vid), 'classification': 'BLOCKED', 'codes': ['NOT_FOUND'], 'detail': 'Vacation not found', 'employee_id': None})
        if not confirm_warnings and any((p['classification'] == 'WARNING' for p in preview)):
            return {'status': 'confirmation_required', 'items': preview, 'approved': [], 'skipped_blocked': [p for p in preview if p['classification'] == 'BLOCKED'], 'failed': []}
        approved: list[dict[str, Any]] = []
        skipped = [p for p in preview if p['classification'] == 'BLOCKED']
        failed: list[dict[str, Any]] = []
        for item in preview:
            if item['classification'] == 'BLOCKED':
                continue
            if item['classification'] == 'WARNING' and (not confirm_warnings):
                continue
            try:
                vac = await self.approve(organization_id, UUID(item['id']), actor_user_id=actor_user_id, confirm_warnings=True)
                approved.append({'id': str(vac.id), 'status': vac.review_status})
            except Exception as exc:
                failed.append({'id': item['id'], 'error': str(exc)})
        await self._audit.append(AuditLogEntry(action='sick_leave.bulk_approved', resource_type='sick_leave_request', organization_id=organization_id, user_id=actor_user_id, details={'requested': len(sick_leave_ids), 'approved': len(approved), 'skipped': len(skipped), 'failed': len(failed), 'confirm_warnings': confirm_warnings}))
        return {'status': 'partial' if failed or (skipped and approved) else 'completed' if approved else 'no_approvals', 'items': preview, 'approved': approved, 'skipped_blocked': skipped, 'failed': failed}

    async def unseen_count(self, organization_id: UUID) -> int:
        return await self._sick_leaves.count_unseen(organization_id)

    async def mark_seen(self, organization_id: UUID, *, sick_leave_ids: list[UUID] | None=None, seen_before: datetime | None=None) -> int:
        return await self._sick_leaves.mark_seen(organization_id, sick_leave_ids=sick_leave_ids, seen_before=seen_before, seen_at=_now())

    async def ingest_inbound(self, organization_id: UUID, command: InboundSickLeaveCommand, *, include_notification: bool=True) -> dict[str, Any]:
        settings = await self._settings.get(organization_id)
        provider = (command.provider or 'gmail').strip().lower()
        message_id = (command.provider_message_id or '').strip()
        if not message_id:
            summary = 'Inbound sick leave rejected: missing provider_message_id. NOT stored.'
            return {'outcome': 'FAILED', 'durable': False, 'sick_leave_request_id': None, 'attention_codes': ['INVALID_PROVIDER_MESSAGE_ID'], 'summary_code': 'INVALID_PROVIDER_MESSAGE_ID', 'summary': summary, 'notification': build_notification_instructions(settings=settings, outcome='FAILED', durable=False, attention_codes=[], summary=summary), 'prefs_echo': {'notify_on_new_sick_leave': settings.notify_on_new_sick_leave, 'notify_on_sick_leave_error_or_attention': settings.notify_on_sick_leave_error_or_attention}}
        existing = await self._sick_leaves.get_by_provider_message(organization_id, provider=provider, provider_message_id=message_id)
        if existing is not None:
            summary = 'Duplicate provider message; existing sick leave returned.'
            return {'outcome': 'DUPLICATE', 'durable': True, 'sick_leave_request_id': str(existing.id), 'attention_codes': [], 'summary_code': 'DUPLICATE_PROVIDER_MESSAGE', 'summary': summary, 'notification': build_notification_instructions(settings=settings, outcome='DUPLICATE', durable=True, attention_codes=[], summary=summary), 'prefs_echo': {'notify_on_new_sick_leave': settings.notify_on_new_sick_leave, 'notify_on_sick_leave_error_or_attention': settings.notify_on_sick_leave_error_or_attention}}
        classification = (command.classification or 'SICK_LEAVE').upper()
        if classification != 'SICK_LEAVE':
            summary = f'Classification {classification} ignored by sick leave ingest.'
            return {'outcome': 'IGNORED', 'durable': False, 'sick_leave_request_id': None, 'attention_codes': [], 'summary_code': 'IGNORED_CLASSIFICATION', 'summary': summary, 'notification': build_notification_instructions(settings=settings, outcome='IGNORED', durable=False, attention_codes=[], summary=summary), 'prefs_echo': {'notify_on_new_sick_leave': settings.notify_on_new_sick_leave, 'notify_on_sick_leave_error_or_attention': settings.notify_on_sick_leave_error_or_attention}}
        start = _parse_date(command.start_date)
        end = _parse_date(command.end_date)
        codes = list(command.n8n_attention_codes or [])
        if command.start_date and start is None:
            codes.append(SickLeaveAttentionCode.INVALID_DATE.value)
        if command.end_date and end is None:
            codes.append(SickLeaveAttentionCode.INVALID_DATE.value)
        codes.extend(collect_date_attention_codes(start, end))
        email = normalize_email(command.employee_email) or normalize_email(command.from_email)
        match = await match_employee_by_email(self._employees, organization_id, email)
        if match.code:
            codes.append(match.code)
        employee_id = match.employee.id if match.employee else None
        confidence = command.confidence
        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            codes.append(SickLeaveAttentionCode.LOW_CONFIDENCE.value)
        if employee_id and start and end:
            overlaps = await find_sick_leave_overlaps(self._sick_leaves, organization_id, employee_id=employee_id, start_date=start, end_date=end)
            if overlaps:
                codes.append(SickLeaveAttentionCode.OVERLAP.value)
            intent_early = (command.intent or SickLeaveIntent.NEW.value).lower()
            if intent_early not in {i.value for i in SickLeaveIntent}:
                intent_early = SickLeaveIntent.UNKNOWN.value
            if intent_early == SickLeaveIntent.NEW.value:
                dup = await find_sick_leave_duplicate_content(self._sick_leaves, organization_id, employee_id=employee_id, start_date=start, end_date=end)
                if dup:
                    summary = 'Exact business duplicate of an existing leave request; existing sick leave returned.'
                    return {'outcome': 'DUPLICATE', 'durable': True, 'sick_leave_request_id': str(dup.id), 'attention_codes': [], 'summary_code': 'DUPLICATE_CONTENT', 'summary': summary, 'notification': build_notification_instructions(settings=settings, outcome='DUPLICATE', durable=True, attention_codes=[], summary=summary), 'prefs_echo': {'notify_on_new_sick_leave': settings.notify_on_new_sick_leave, 'notify_on_sick_leave_error_or_attention': settings.notify_on_sick_leave_error_or_attention}}
        intent = (command.intent or SickLeaveIntent.NEW.value).lower()
        if intent not in {i.value for i in SickLeaveIntent}:
            intent = SickLeaveIntent.UNKNOWN.value
        related_id, related_code = await resolve_related_sick_leave(self._sick_leaves, organization_id, intent=intent, employee_id=employee_id, start_date=start, end_date=end, target_hints=command.target_hints)
        if related_code:
            codes.append(related_code)
        uniq_codes = self._unique_codes(codes)
        needs_attention = bool(set(uniq_codes) & HARD_BLOCK_CODES) or intent in {SickLeaveIntent.UPDATE.value, SickLeaveIntent.CANCEL.value, SickLeaveIntent.UNKNOWN.value}
        status = SickLeaveReviewStatus.REQUIRES_ATTENTION.value if needs_attention else SickLeaveReviewStatus.PENDING_APPROVAL.value
        body = command.body_text or ''
        body_s3 = None
        if len(body) > MAX_BODY_INLINE_CHARS:
            full_body = body
            body = body[:MAX_BODY_INLINE_CHARS]
            if self._object_storage is not None:
                try:
                    key = f'sick-leaves/{organization_id}/{provider}/{message_id[:200]}.txt'
                    await self._object_storage.upload(key, full_body.encode('utf-8'), 'text/plain; charset=utf-8')
                    body_s3 = key
                except Exception:
                    logger.warning('Failed to upload oversized vacation body to S3; keeping truncated inline preview only', exc_info=True)
        explanation = (command.explanation or '')[:2000] or None
        vac = SickLeaveRequest(id=uuid4(), organization_id=organization_id, employee_id=employee_id, extracted_employee_email=email, extracted_employee_name=command.employee_name, sender_email=normalize_email(command.from_email), start_date=start, end_date=end, provider=provider, provider_message_id=message_id, provider_thread_id=command.provider_thread_id, original_subject=(command.subject or '')[:500], original_body_text=body, original_body_s3_key=body_s3, received_at=command.received_at or _now(), ai_confidence=confidence, ai_explanation=explanation, ai_extraction_original=self._snapshot_ai_extraction(employee_email=email, employee_name=command.employee_name, start_date=start, end_date=end, confidence=confidence, explanation=explanation), intent=intent, related_sick_leave_id=related_id, source=SickLeaveSource.EMAIL.value, review_status=status, attention_codes=uniq_codes, overlap_with=[], created_at=_now(), updated_at=_now())
        if vac.employee_id and vac.start_date and vac.end_date:
            peer_overlaps = await find_sick_leave_overlaps(self._sick_leaves, organization_id, employee_id=vac.employee_id, start_date=vac.start_date, end_date=vac.end_date, exclude_id=vac.id)
            vac.overlap_with = [o.id for o in peer_overlaps]
            if peer_overlaps and SickLeaveAttentionCode.OVERLAP.value not in vac.attention_codes:
                vac.attention_codes = self._unique_codes([*vac.attention_codes, SickLeaveAttentionCode.OVERLAP.value])
                if not needs_attention:
                    vac.review_status = SickLeaveReviewStatus.PENDING_APPROVAL.value
        saved = await self._sick_leaves.save(vac)
        await self._refresh_overlap_peers(organization_id, employee_id=saved.employee_id, exclude_id=saved.id, previous_peer_ids=list(saved.overlap_with or []))
        await self._audit.append(AuditLogEntry(action='sick_leave.ingested', resource_type='sick_leave_request', resource_id=saved.id, organization_id=organization_id, details={'provider': provider, 'provider_message_id': message_id, 'status': vac.review_status, 'attention_codes': list(vac.attention_codes or [])}))
        outcome = 'REQUIRES_ATTENTION' if vac.review_status == SickLeaveReviewStatus.REQUIRES_ATTENTION.value else 'SUCCESS'
        summary = f"Sick leave request stored ({outcome}). Employee email={email or 'missing'}; dates={start}..{end}; codes={','.join(vac.attention_codes) or 'none'}."
        if SickLeaveAttentionCode.EMPLOYEE_NOT_FOUND.value in vac.attention_codes:
            summary = f'Sick leave request was received but no employee with email {email} exists in Payroll Copilot. Manual review is required. STORED BUT NEEDS ATTENTION.'
        return {'outcome': outcome, 'durable': True, 'sick_leave_request_id': str(saved.id), 'attention_codes': list(vac.attention_codes or []), 'summary_code': vac.attention_codes[0] if vac.attention_codes else outcome, 'summary': summary, 'notification': build_notification_instructions(settings=settings, outcome=outcome, durable=True, attention_codes=list(vac.attention_codes or []), summary=summary), 'prefs_echo': {'notify_on_new_sick_leave': settings.notify_on_new_sick_leave, 'notify_on_sick_leave_error_or_attention': settings.notify_on_sick_leave_error_or_attention}}
