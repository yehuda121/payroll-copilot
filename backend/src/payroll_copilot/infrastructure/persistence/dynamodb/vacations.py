"""DynamoDB VacationRequest repository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from payroll_copilot.application.ports.vacation_requests import (
    VacationListFilter,
    VacationRequestRepository,
)
from payroll_copilot.domain.entities import VacationRequest
from payroll_copilot.domain.enums import VacationReviewStatus
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


def _matches_bucket(vac: VacationRequest, bucket: str, today: date) -> bool:
    status = vac.review_status
    start = vac.start_date
    end = vac.end_date
    if bucket == "pending_approval":
        return status == VacationReviewStatus.PENDING_APPROVAL.value
    if bucket == "requires_attention":
        return status == VacationReviewStatus.REQUIRES_ATTENTION.value
    if bucket == "approved":
        return status == VacationReviewStatus.APPROVED.value
    if bucket == "active":
        # Default Leave Management inbox: unresolved + approved not fully past.
        if status in {
            VacationReviewStatus.PENDING_APPROVAL.value,
            VacationReviewStatus.REQUIRES_ATTENTION.value,
        }:
            return True
        if status == VacationReviewStatus.APPROVED.value:
            if end is None:
                # Incomplete approved end date — keep visible so it cannot vanish.
                return True
            return end >= today
        return False
    if bucket == "current":
        return (
            status == VacationReviewStatus.APPROVED.value
            and start is not None
            and end is not None
            and start <= today <= end
        )
    if bucket == "upcoming":
        return (
            status == VacationReviewStatus.APPROVED.value
            and start is not None
            and start > today
        )
    if bucket == "past":
        if status in {
            VacationReviewStatus.REJECTED.value,
            VacationReviewStatus.CANCELLED.value,
        }:
            return True
        return (
            status == VacationReviewStatus.APPROVED.value
            and end is not None
            and end < today
        )
    return True


class DynamoVacationRequestRepository(VacationRequestRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _to_item(self, vacation: VacationRequest) -> dict:
        emp_key = vacation.employee_id
        item: dict = {
            "PK": keys.org_pk(vacation.organization_id),
            "SK": keys.vac_sk(vacation.id),
            "entity_type": "vacation_request",
            "GSI1PK": keys.gsi1_vac(vacation.id),
            "GSI1SK": keys.org_pk(vacation.organization_id),
            "GSI3PK": keys.gsi3_vac_employee(vacation.organization_id, emp_key),
            "GSI3SK": keys.vac_sk(vacation.id),
            "id": str(vacation.id),
            "organization_id": str(vacation.organization_id),
            "employee_id": dumps_value(vacation.employee_id),
            "extracted_employee_email": vacation.extracted_employee_email,
            "extracted_employee_name": vacation.extracted_employee_name,
            "sender_email": vacation.sender_email,
            "start_date": dumps_value(vacation.start_date),
            "end_date": dumps_value(vacation.end_date),
            "provider": vacation.provider,
            "provider_message_id": vacation.provider_message_id,
            "provider_thread_id": vacation.provider_thread_id,
            "original_subject": vacation.original_subject,
            "original_body_text": vacation.original_body_text,
            "original_body_s3_key": vacation.original_body_s3_key,
            "received_at": dumps_value(vacation.received_at),
            "ai_confidence": dumps_value(vacation.ai_confidence),
            "ai_explanation": vacation.ai_explanation,
            "ai_extraction_original": dumps_value(vacation.ai_extraction_original),
            "intent": vacation.intent,
            "related_vacation_id": dumps_value(vacation.related_vacation_id),
            "source": vacation.source,
            "review_status": vacation.review_status,
            "attention_codes": list(vacation.attention_codes or []),
            "attention_detail": vacation.attention_detail,
            "overlap_with": [str(x) for x in (vacation.overlap_with or [])],
            "seen_at": dumps_value(vacation.seen_at),
            "created_at": dumps_value(vacation.created_at),
            "updated_at": dumps_value(vacation.updated_at),
            "created_by": dumps_value(vacation.created_by),
            "approved_by": dumps_value(vacation.approved_by),
            "approved_at": dumps_value(vacation.approved_at),
        }
        if vacation.provider and vacation.provider_message_id:
            item["GSI2PK"] = keys.gsi2_vac_message(
                vacation.organization_id,
                vacation.provider,
                vacation.provider_message_id,
            )
            item["GSI2SK"] = keys.vac_sk(vacation.id)
        return {k: v for k, v in item.items() if v is not None}

    def _to_entity(self, item: dict) -> VacationRequest:
        return VacationRequest(
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
            related_vacation_id=loads_uuid(item.get("related_vacation_id")),
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
        self, organization_id: UUID, vacation_id: UUID
    ) -> VacationRequest | None:
        item = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.vac_sk(vacation_id)}
        )
        if item is None or item.get("entity_type") != "vacation_request":
            return None
        return self._to_entity(item)

    async def get_by_provider_message(
        self,
        organization_id: UUID,
        *,
        provider: str,
        provider_message_id: str,
    ) -> VacationRequest | None:
        items = await self._table.query_eq_pk(
            keys.gsi2_vac_message(organization_id, provider, provider_message_id),
            index_name=GSI2,
            limit=5,
        )
        for item in items:
            if item.get("entity_type") == "vacation_request":
                return self._to_entity(item)
        return None

    async def list(self, filters: VacationListFilter) -> list[VacationRequest]:
        items = await self._table.query_eq_pk(
            keys.org_pk(filters.organization_id),
            sk_begins_with="VAC#",
        )
        vacations = [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "vacation_request" and item.get("id")
        ]
        today = _today()
        if filters.bucket:
            vacations = [v for v in vacations if _matches_bucket(v, filters.bucket, today)]
        if filters.range_start is not None and filters.range_end is not None:
            vacations = [
                v
                for v in vacations
                if _intervals_overlap(
                    v.start_date, v.end_date, filters.range_start, filters.range_end
                )
            ]
        if filters.employee_id is not None:
            vacations = [v for v in vacations if v.employee_id == filters.employee_id]
        if filters.query:
            needle = filters.query.strip().lower()
            vacations = [
                v
                for v in vacations
                if needle in (v.extracted_employee_email or "").lower()
                or needle in (v.extracted_employee_name or "").lower()
                or needle in (v.sender_email or "").lower()
                or needle in (v.original_subject or "").lower()
            ]
        vacations.sort(
            key=lambda v: (
                v.start_date or date.min,
                v.created_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        start = max(0, filters.offset)
        end = start + min(max(1, filters.limit), 500)
        return vacations[start:end]

    async def list_for_employee(
        self, organization_id: UUID, employee_id: UUID
    ) -> list[VacationRequest]:
        items = await self._table.query_eq_pk(
            keys.gsi3_vac_employee(organization_id, employee_id),
            index_name="GSI3",
        )
        return [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "vacation_request"
        ]

    async def save(self, vacation: VacationRequest) -> VacationRequest:
        vacation.updated_at = datetime.now(UTC)
        await self._table.put_item(self._to_item(vacation))
        return vacation

    async def delete(self, organization_id: UUID, vacation_id: UUID) -> None:
        await self._table.delete_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.vac_sk(vacation_id)}
        )

    async def count_unseen(self, organization_id: UUID) -> int:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="VAC#",
        )
        count = 0
        for item in items:
            if item.get("entity_type") != "vacation_request":
                continue
            status = str(item.get("review_status") or "")
            if status not in {
                VacationReviewStatus.PENDING_APPROVAL.value,
                VacationReviewStatus.REQUIRES_ATTENTION.value,
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
        vacation_ids: list[UUID] | None = None,
        seen_before: datetime | None = None,
        seen_at: datetime,
    ) -> int:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="VAC#",
        )
        id_set = {str(i) for i in vacation_ids} if vacation_ids else None
        updated = 0
        for item in items:
            if item.get("entity_type") != "vacation_request":
                continue
            vac = self._to_entity(item)
            if id_set is not None and str(vac.id) not in id_set:
                continue
            if seen_before is not None and vac.created_at and vac.created_at > seen_before:
                continue
            if vac.review_status not in {
                VacationReviewStatus.PENDING_APPROVAL.value,
                VacationReviewStatus.REQUIRES_ATTENTION.value,
            }:
                continue
            if vac.seen_at is not None:
                continue
            vac.seen_at = seen_at
            await self.save(vac)
            updated += 1
        return updated
