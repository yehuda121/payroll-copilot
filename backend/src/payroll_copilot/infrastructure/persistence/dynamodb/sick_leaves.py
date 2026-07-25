"""DynamoDB SickLeaveRequest repository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from payroll_copilot.application.ports.sick_leave_requests import (
    SickLeaveListFilter,
    SickLeaveRequestRepository,
)
from payroll_copilot.domain.entities import SickLeaveRequest
from payroll_copilot.domain.enums import SickLeaveReviewStatus
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, GSI2, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    dumps_value,
    loads_date,
    loads_datetime,
    loads_float,
    loads_uuid,
)


def _today() -> date:
    return datetime.now(UTC).date()


def _intervals_overlap(
    start_a: date | None,
    end_a: date | None,
    start_b: date | None,
    end_b: date | None,
) -> bool:
    if start_a is None or end_a is None or start_b is None or end_b is None:
        return False
    return start_a <= end_b and end_a >= start_b


def _matches_bucket(rec: SickLeaveRequest, bucket: str, today: date) -> bool:
    status = rec.review_status
    start = rec.start_date
    end = rec.end_date
    if bucket == "pending_approval":
        return status == SickLeaveReviewStatus.PENDING_APPROVAL.value
    if bucket == "requires_attention":
        return status == SickLeaveReviewStatus.REQUIRES_ATTENTION.value
    if bucket == "approved":
        return status == SickLeaveReviewStatus.APPROVED.value
    if bucket == "active":
        # Default Leave Management inbox: unresolved + approved not fully past.
        if status in {
            SickLeaveReviewStatus.PENDING_APPROVAL.value,
            SickLeaveReviewStatus.REQUIRES_ATTENTION.value,
        }:
            return True
        if status == SickLeaveReviewStatus.APPROVED.value:
            if end is None:
                # Incomplete approved end date — keep visible so it cannot vanish.
                return True
            return end >= today
        return False
    if bucket == "current":
        return (
            status == SickLeaveReviewStatus.APPROVED.value
            and start is not None
            and end is not None
            and start <= today <= end
        )
    if bucket == "upcoming":
        return (
            status == SickLeaveReviewStatus.APPROVED.value
            and start is not None
            and start > today
        )
    if bucket == "past":
        if status in {
            SickLeaveReviewStatus.REJECTED.value,
            SickLeaveReviewStatus.CANCELLED.value,
        }:
            return True
        return (
            status == SickLeaveReviewStatus.APPROVED.value
            and end is not None
            and end < today
        )
    return True


class DynamoSickLeaveRequestRepository(SickLeaveRequestRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _to_item(self, sick_leave: SickLeaveRequest) -> dict:
        emp_key = sick_leave.employee_id
        item: dict = {
            "PK": keys.org_pk(sick_leave.organization_id),
            "SK": keys.sick_sk(sick_leave.id),
            "entity_type": "sick_leave_request",
            "GSI1PK": keys.gsi1_sick(sick_leave.id),
            "GSI1SK": keys.org_pk(sick_leave.organization_id),
            "GSI3PK": keys.gsi3_sick_employee(sick_leave.organization_id, emp_key),
            "GSI3SK": keys.sick_sk(sick_leave.id),
            "id": str(sick_leave.id),
            "organization_id": str(sick_leave.organization_id),
            "employee_id": dumps_value(sick_leave.employee_id),
            "extracted_employee_email": sick_leave.extracted_employee_email,
            "extracted_employee_name": sick_leave.extracted_employee_name,
            "sender_email": sick_leave.sender_email,
            "start_date": dumps_value(sick_leave.start_date),
            "end_date": dumps_value(sick_leave.end_date),
            "provider": sick_leave.provider,
            "provider_message_id": sick_leave.provider_message_id,
            "provider_thread_id": sick_leave.provider_thread_id,
            "original_subject": sick_leave.original_subject,
            "original_body_text": sick_leave.original_body_text,
            "original_body_s3_key": sick_leave.original_body_s3_key,
            "received_at": dumps_value(sick_leave.received_at),
            "ai_confidence": dumps_value(sick_leave.ai_confidence),
            "ai_explanation": sick_leave.ai_explanation,
            "ai_extraction_original": dumps_value(sick_leave.ai_extraction_original),
            "intent": sick_leave.intent,
            "related_sick_leave_id": dumps_value(sick_leave.related_sick_leave_id),
            "source": sick_leave.source,
            "review_status": sick_leave.review_status,
            "attention_codes": list(sick_leave.attention_codes or []),
            "attention_detail": sick_leave.attention_detail,
            "overlap_with": [str(x) for x in (sick_leave.overlap_with or [])],
            "seen_at": dumps_value(sick_leave.seen_at),
            "created_at": dumps_value(sick_leave.created_at),
            "updated_at": dumps_value(sick_leave.updated_at),
            "created_by": dumps_value(sick_leave.created_by),
            "approved_by": dumps_value(sick_leave.approved_by),
            "approved_at": dumps_value(sick_leave.approved_at),
        }
        if sick_leave.provider and sick_leave.provider_message_id:
            item["GSI2PK"] = keys.gsi2_sick_message(
                sick_leave.organization_id,
                sick_leave.provider,
                sick_leave.provider_message_id,
            )
            item["GSI2SK"] = keys.sick_sk(sick_leave.id)
        return {k: v for k, v in item.items() if v is not None}

    def _to_entity(self, item: dict) -> SickLeaveRequest:
        return SickLeaveRequest(
            id=UUID(str(item["id"])),
            organization_id=UUID(str(item["organization_id"])),
            employee_id=loads_uuid(item.get("employee_id")),
            extracted_employee_email=item.get("extracted_employee_email"),
            extracted_employee_name=item.get("extracted_employee_name"),
            sender_email=item.get("sender_email"),
            start_date=loads_date(item.get("start_date")),
            end_date=loads_date(item.get("end_date")),
            provider=item.get("provider"),
            provider_message_id=item.get("provider_message_id"),
            provider_thread_id=item.get("provider_thread_id"),
            original_subject=item.get("original_subject"),
            original_body_text=item.get("original_body_text"),
            original_body_s3_key=item.get("original_body_s3_key"),
            received_at=loads_datetime(item.get("received_at")),
            ai_confidence=loads_float(item.get("ai_confidence")),
            ai_explanation=item.get("ai_explanation"),
            ai_extraction_original=(
                dict(item["ai_extraction_original"])
                if isinstance(item.get("ai_extraction_original"), dict)
                else None
            ),
            intent=str(item.get("intent") or "new"),
            related_sick_leave_id=loads_uuid(item.get("related_sick_leave_id")),
            source=str(item.get("source") or "manual"),
            review_status=str(item.get("review_status") or "pending_approval"),
            attention_codes=[str(c) for c in (item.get("attention_codes") or [])],
            attention_detail=item.get("attention_detail"),
            overlap_with=[
                uid
                for raw in (item.get("overlap_with") or [])
                if (uid := loads_uuid(raw)) is not None
            ],
            seen_at=loads_datetime(item.get("seen_at")),
            created_at=loads_datetime(item.get("created_at")) or datetime.now(UTC),
            updated_at=loads_datetime(item.get("updated_at")) or datetime.now(UTC),
            created_by=loads_uuid(item.get("created_by")),
            approved_by=loads_uuid(item.get("approved_by")),
            approved_at=loads_datetime(item.get("approved_at")),
        )

    async def get_by_id(
        self, organization_id: UUID, sick_leave_id: UUID
    ) -> SickLeaveRequest | None:
        item = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.sick_sk(sick_leave_id)}
        )
        if item is None or item.get("entity_type") != "sick_leave_request":
            return None
        return self._to_entity(item)

    async def get_by_provider_message(
        self,
        organization_id: UUID,
        *,
        provider: str,
        provider_message_id: str,
    ) -> SickLeaveRequest | None:
        items = await self._table.query_eq_pk(
            keys.gsi2_sick_message(organization_id, provider, provider_message_id),
            index_name=GSI2,
            limit=5,
        )
        for item in items:
            if item.get("entity_type") == "sick_leave_request":
                return self._to_entity(item)
        return None

    async def list(self, filters: SickLeaveListFilter) -> list[SickLeaveRequest]:
        items = await self._table.query_eq_pk(
            keys.org_pk(filters.organization_id),
            sk_begins_with="SICK#",
        )
        sick_leaves = [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "sick_leave_request" and item.get("id")
        ]
        today = _today()
        if filters.bucket:
            sick_leaves = [v for v in sick_leaves if _matches_bucket(v, filters.bucket, today)]
        if filters.range_start is not None and filters.range_end is not None:
            sick_leaves = [
                v
                for v in sick_leaves
                if _intervals_overlap(
                    v.start_date, v.end_date, filters.range_start, filters.range_end
                )
            ]
        if filters.employee_id is not None:
            sick_leaves = [v for v in sick_leaves if v.employee_id == filters.employee_id]
        if filters.query:
            needle = filters.query.strip().lower()
            sick_leaves = [
                v
                for v in sick_leaves
                if needle in (v.extracted_employee_email or "").lower()
                or needle in (v.extracted_employee_name or "").lower()
                or needle in (v.sender_email or "").lower()
                or needle in (v.original_subject or "").lower()
            ]
        sick_leaves.sort(
            key=lambda v: (
                v.start_date or date.min,
                v.created_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        start = max(0, filters.offset)
        end = start + min(max(1, filters.limit), 500)
        return sick_leaves[start:end]

    async def list_for_employee(
        self, organization_id: UUID, employee_id: UUID
    ) -> list[SickLeaveRequest]:
        items = await self._table.query_eq_pk(
            keys.gsi3_sick_employee(organization_id, employee_id),
            index_name="GSI3",
        )
        return [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "sick_leave_request"
        ]

    async def save(self, sick_leave: SickLeaveRequest) -> SickLeaveRequest:
        sick_leave.updated_at = datetime.now(UTC)
        await self._table.put_item(self._to_item(sick_leave))
        return sick_leave

    async def delete(self, organization_id: UUID, sick_leave_id: UUID) -> None:
        await self._table.delete_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.sick_sk(sick_leave_id)}
        )

    async def count_unseen(self, organization_id: UUID) -> int:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="SICK#",
        )
        count = 0
        for item in items:
            if item.get("entity_type") != "sick_leave_request":
                continue
            status = str(item.get("review_status") or "")
            if status not in {
                SickLeaveReviewStatus.PENDING_APPROVAL.value,
                SickLeaveReviewStatus.REQUIRES_ATTENTION.value,
            }:
                continue
            if item.get("seen_at"):
                continue
            count += 1
        return count

    async def mark_seen(
        self,
        organization_id: UUID,
        *,
        sick_leave_ids: list[UUID] | None = None,
        seen_before: datetime | None = None,
        seen_at: datetime,
    ) -> int:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="SICK#",
        )
        id_set = {str(i) for i in sick_leave_ids} if sick_leave_ids else None
        updated = 0
        for item in items:
            if item.get("entity_type") != "sick_leave_request":
                continue
            rec = self._to_entity(item)
            if id_set is not None and str(rec.id) not in id_set:
                continue
            if seen_before is not None and rec.created_at and rec.created_at > seen_before:
                continue
            if rec.review_status not in {
                SickLeaveReviewStatus.PENDING_APPROVAL.value,
                SickLeaveReviewStatus.REQUIRES_ATTENTION.value,
            }:
                continue
            if rec.seen_at is not None:
                continue
            rec.seen_at = seen_at
            await self.save(rec)
            updated += 1
        return updated
