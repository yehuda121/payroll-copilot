"""DynamoDB document repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from payroll_copilot.application.ports.repositories import DocumentRepository
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentStatus, DocumentType
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    dumps_value,
    loads_datetime,
    loads_uuid,
)


class DynamoDocumentRepository(DocumentRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _partition(self, document: Document) -> tuple[str, str]:
        org_id = document.organization_id
        if org_id is None:
            pk = f"DOCROOT#{document.id}"
            sk = "META"
            return pk, sk
        if document.employee_id is not None:
            period_year = document.period.year if document.period else None
            period_month = document.period.month if document.period else None
            return (
                keys.emp_pk(org_id, document.employee_id),
                keys.doc_sk(
                    document_type=document.document_type.value
                    if hasattr(document.document_type, "value")
                    else str(document.document_type),
                    period_year=period_year,
                    period_month=period_month,
                    document_id=document.id,
                ),
            )
        return keys.org_pk(org_id), keys.guest_doc_sk(document.id)

    def _to_item(self, document: Document) -> dict:
        pk, sk = self._partition(document)
        meta = dict(document.metadata or {})
        item: dict = {
            "PK": pk,
            "SK": sk,
            "entity_type": "document",
            "GSI1PK": keys.gsi1_doc(document.id),
            "GSI1SK": "META",
            "id": str(document.id),
            "organization_id": dumps_value(document.organization_id),
            "uploaded_by": dumps_value(document.uploaded_by),
            "document_type": dumps_value(document.document_type),
            "storage_key": document.storage_key,
            "original_filename": document.original_filename,
            "mime_type": document.mime_type,
            "file_size_bytes": document.file_size_bytes,
            "checksum_sha256": document.checksum_sha256,
            "status": dumps_value(document.status),
            "employee_id": dumps_value(document.employee_id),
            "period_year": document.period.year if document.period else None,
            "period_month": document.period.month if document.period else None,
            "metadata": dumps_value(meta),
            "created_at": dumps_value(document.created_at),
            "expires_at": dumps_value(document.expires_at),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        dataset_id = meta.get("dataset_id")
        if dataset_id:
            item["GSI3PK"] = keys.gsi3_dataset(str(dataset_id))
            item["GSI3SK"] = keys.gsi1_doc(document.id)
            item["dataset_id"] = str(dataset_id)
        return {k: v for k, v in item.items() if v is not None}

    def _to_entity(self, item: dict) -> Document:
        period = None
        if item.get("period_year") is not None and item.get("period_month") is not None:
            period = PayPeriod(year=int(item["period_year"]), month=int(item["period_month"]))
        return Document(
            id=UUID(str(item["id"])),
            document_type=DocumentType(str(item.get("document_type") or DocumentType.PAYSLIP.value)),
            storage_key=str(item.get("storage_key") or ""),
            original_filename=str(item.get("original_filename") or ""),
            mime_type=str(item.get("mime_type") or "application/octet-stream"),
            file_size_bytes=int(item.get("file_size_bytes") or 0),
            checksum_sha256=str(item.get("checksum_sha256") or ""),
            status=DocumentStatus(str(item.get("status") or DocumentStatus.UPLOADED.value)),
            organization_id=loads_uuid(item.get("organization_id")),
            uploaded_by=loads_uuid(item.get("uploaded_by")),
            employee_id=loads_uuid(item.get("employee_id")),
            period=period,
            metadata=dict(item.get("metadata") or {}),
            created_at=loads_datetime(item.get("created_at")) or datetime.now(UTC),
            expires_at=loads_datetime(item.get("expires_at")),
        )

    async def get_by_id(self, document_id: UUID) -> Document | None:
        items = await self._table.query_eq_pk(keys.gsi1_doc(document_id), index_name=GSI1, limit=1)
        if not items:
            return None
        return self._to_entity(items[0])

    async def save(self, document: Document) -> Document:
        existing_items = await self._table.query_eq_pk(
            keys.gsi1_doc(document.id), index_name=GSI1, limit=1
        )
        new_item = self._to_item(document)
        if existing_items:
            old = existing_items[0]
            if old.get("PK") != new_item["PK"] or old.get("SK") != new_item["SK"]:
                await self._table.delete_item({"PK": old["PK"], "SK": old["SK"]})
        await self._table.put_item(new_item)
        return document

    async def list_for_employee(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
    ) -> list[Document]:
        items = await self._table.query_eq_pk(
            keys.emp_pk(organization_id, employee_id),
            sk_begins_with="DOC#",
            scan_index_forward=False,
        )
        docs = [self._to_entity(item) for item in items]
        docs.sort(
            key=lambda d: (
                -(d.period.year if d.period else 0),
                -(d.period.month if d.period else 0),
            )
        )
        return docs

    async def find_payslip_for_period(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period_year: int,
        period_month: int,
    ) -> Document | None:
        prefix = f"DOC#{DocumentType.PAYSLIP.value}#{period_year:04d}-{period_month:02d}#"
        items = await self._table.query_eq_pk(
            keys.emp_pk(organization_id, employee_id),
            sk_begins_with=prefix,
            scan_index_forward=False,
            limit=1,
        )
        if not items:
            return None
        return self._to_entity(items[0])

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Document]:
        from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI3

        items = await self._table.query_eq_pk(keys.gsi3_dataset(dataset_id), index_name=GSI3)
        return [self._to_entity(item) for item in items if item.get("entity_type") == "document"]

    async def delete_by_ids(self, document_ids: list[UUID]) -> int:
        keys_to_delete: list[dict] = []
        for document_id in document_ids:
            items = await self._table.query_eq_pk(
                keys.gsi1_doc(document_id), index_name=GSI1, limit=1
            )
            for item in items:
                keys_to_delete.append({"PK": item["PK"], "SK": item["SK"]})
        return await self._table.batch_delete(keys_to_delete)
