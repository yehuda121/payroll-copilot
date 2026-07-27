"""DynamoDB document extraction repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.repositories import DocumentExtractionRepository
from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.extraction_artifacts import (
    STORAGE_KEY_FIELDS,
    best_effort_delete_keys,
    hydrate_extraction_artifacts,
    prepare_extraction_item_for_put,
)
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    dumps_value,
    is_empty_for_storage,
    loads_datetime,
    loads_float,
    loads_uuid,
    prune_empty,
)

# Top-level Dynamo keys that must survive pruning even when empty-ish.
_REQUIRED_EXTRACTION_KEYS = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "GSI1PK",
        "GSI1SK",
        "id",
        "document_id",
        "extraction_version",
        "confirmation_status",
        "ocr_status",
        "parser_status",
        "created_at",
        "updated_at",
    }
)


class DynamoDocumentExtractionRepository(DocumentExtractionRepository):
    def __init__(
        self,
        table: DynamoTable,
        *,
        object_storage: ObjectStoragePort | None = None,
    ) -> None:
        self._table = table
        self._storage = object_storage

    def _to_item(self, extraction: DocumentExtraction) -> dict:
        now = datetime.now(UTC).isoformat()
        item = {
            "PK": keys.gsi1_doc(extraction.document_id),
            "SK": keys.ext_sk(version=extraction.extraction_version, extraction_id=extraction.id),
            "entity_type": "extraction",
            "GSI1PK": keys.gsi1_ext(extraction.id),
            "GSI1SK": "META",
            "id": str(extraction.id),
            "document_id": str(extraction.document_id),
            "engine": extraction.engine,
            "raw_text": extraction.raw_text or "",
            "structured_data": dumps_value(extraction.structured_data or {}),
            "overall_confidence": dumps_value(extraction.overall_confidence),
            "field_confidences": dumps_value(extraction.field_confidences or {}),
            "extraction_version": extraction.extraction_version,
            "created_at": dumps_value(extraction.created_at),
            "ocr_result": dumps_value(extraction.ocr_result or {}),
            "layout_snapshot": dumps_value(extraction.layout_snapshot)
            if extraction.layout_snapshot
            else None,
            "layout_analysis": dumps_value(extraction.layout_analysis)
            if extraction.layout_analysis
            else None,
            "ocr_result_storage_key": extraction.ocr_result_storage_key,
            "layout_snapshot_storage_key": extraction.layout_snapshot_storage_key,
            "layout_analysis_storage_key": extraction.layout_analysis_storage_key,
            "parser_model": extraction.parser_model,
            "language": extraction.language or "auto",
            "ocr_status": extraction.ocr_status,
            "parser_status": extraction.parser_status,
            "warnings": list(extraction.warnings or []),
            "error_message": extraction.error_message,
            "updated_at": dumps_value(extraction.updated_at) or now,
            "confirmation_status": extraction.confirmation_status or "review_required",
            "confirmed_at": dumps_value(extraction.confirmed_at),
            "confirmed_by": dumps_value(extraction.confirmed_by),
        }
        return self._prune_item(item)

    @staticmethod
    def _prune_item(item: dict) -> dict:
        """Recursively omit empty values while preserving required Dynamo keys."""
        pruned: dict = {}
        for key, value in item.items():
            cleaned = prune_empty(value)
            if key in _REQUIRED_EXTRACTION_KEYS:
                if is_empty_for_storage(cleaned):
                    # Required identity/lifecycle keys must remain present.
                    if value is None:
                        continue
                    pruned[key] = value
                else:
                    pruned[key] = cleaned
                continue
            if is_empty_for_storage(cleaned):
                continue
            pruned[key] = cleaned
        return pruned

    def _to_entity(self, item: dict) -> DocumentExtraction:
        field_confidences = {
            str(k): float(v)
            for k, v in dict(item.get("field_confidences") or {}).items()
            if v is not None
        }
        return DocumentExtraction(
            id=UUID(str(item["id"])),
            document_id=UUID(str(item["document_id"])),
            engine=str(item.get("engine") or ""),
            raw_text=str(item.get("raw_text") or ""),
            structured_data=dict(item.get("structured_data") or {}),
            overall_confidence=loads_float(item.get("overall_confidence")),
            field_confidences=field_confidences,
            extraction_version=int(item.get("extraction_version") or 1),
            created_at=loads_datetime(item.get("created_at")) or datetime.now(UTC),
            ocr_result=dict(item.get("ocr_result") or {}),
            layout_snapshot=dict(item.get("layout_snapshot") or {}),
            layout_analysis=dict(item.get("layout_analysis") or {}),
            ocr_result_storage_key=item.get("ocr_result_storage_key"),
            layout_snapshot_storage_key=item.get("layout_snapshot_storage_key"),
            layout_analysis_storage_key=item.get("layout_analysis_storage_key"),
            parser_model=item.get("parser_model"),
            language=str(item.get("language") or "auto"),
            ocr_status=str(item.get("ocr_status") or "completed"),
            parser_status=str(item.get("parser_status") or "completed"),
            warnings=list(item.get("warnings") or []),
            error_message=item.get("error_message"),
            updated_at=loads_datetime(item.get("updated_at")) or datetime.now(UTC),
            confirmation_status=str(item.get("confirmation_status") or "review_required"),
            confirmed_at=loads_datetime(item.get("confirmed_at")),
            confirmed_by=loads_uuid(item.get("confirmed_by")),
        )

    async def _hydrate(self, entity: DocumentExtraction) -> DocumentExtraction:
        storage_keys = {
            "ocr_result_storage_key": entity.ocr_result_storage_key,
            "layout_snapshot_storage_key": entity.layout_snapshot_storage_key,
            "layout_analysis_storage_key": entity.layout_analysis_storage_key,
        }
        if not any(storage_keys.values()):
            return entity
        needs_load = (
            (entity.ocr_result_storage_key and not entity.ocr_result)
            or (entity.layout_analysis_storage_key and not entity.layout_analysis)
            or (entity.layout_snapshot_storage_key and not entity.layout_snapshot)
        )
        if not needs_load:
            return entity
        hydrated = await hydrate_extraction_artifacts(
            entity_fields={
                "ocr_result": entity.ocr_result,
                "layout_snapshot": entity.layout_snapshot,
                "layout_analysis": entity.layout_analysis,
            },
            storage_keys=storage_keys,
            object_storage=self._storage,
        )
        entity.ocr_result = dict(hydrated.get("ocr_result") or {})
        entity.layout_snapshot = dict(hydrated.get("layout_snapshot") or {})
        entity.layout_analysis = dict(hydrated.get("layout_analysis") or {})
        return entity

    async def get_by_id(self, extraction_id: UUID) -> DocumentExtraction | None:
        items = await self._table.query_eq_pk(keys.gsi1_ext(extraction_id), index_name=GSI1, limit=1)
        if not items:
            return None
        return await self._hydrate(self._to_entity(items[0]))

    async def get_latest_for_document(self, document_id: UUID) -> DocumentExtraction | None:
        items = await self._table.query_eq_pk(
            keys.gsi1_doc(document_id),
            sk_begins_with="EXT#",
            scan_index_forward=False,
            limit=1,
        )
        if not items:
            return None
        return await self._hydrate(self._to_entity(items[0]))

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        existing = await self.get_by_id(extraction.id)
        if existing is not None and (
            existing.document_id != extraction.document_id
            or existing.extraction_version != extraction.extraction_version
        ):
            old_items = await self._table.query_eq_pk(
                keys.gsi1_ext(extraction.id), index_name=GSI1, limit=1
            )
            for old in old_items:
                await self._table.delete_item({"PK": old["PK"], "SK": old["SK"]})
        item = self._to_item(extraction)
        # When building from a fully hydrated entity, prefer current inline payloads
        # over stale pointer-only writes for size decisions.
        uploaded_keys: list[str] = []
        try:
            item, uploaded_keys = await prepare_extraction_item_for_put(
                item=item,
                document_id=str(extraction.document_id),
                extraction_id=str(extraction.id),
                extraction_version=extraction.extraction_version,
                object_storage=self._storage,
            )
            await self._table.put_item(item)
        except Exception:
            await best_effort_delete_keys(self._storage, uploaded_keys)
            raise
        # Keep caller's in-memory extraction payloads intact; sync pointer metadata.
        for _field, key_field in STORAGE_KEY_FIELDS.items():
            setattr(extraction, key_field, item.get(key_field))
        return extraction

    async def delete_for_document_ids(self, document_ids: list[UUID]) -> int:
        deleted = 0
        for document_id in document_ids:
            items = await self._table.query_eq_pk(
                keys.gsi1_doc(document_id),
                sk_begins_with="EXT#",
            )
            artifact_keys: list[str] = []
            for item in items:
                for key_field in STORAGE_KEY_FIELDS.values():
                    key = item.get(key_field)
                    if isinstance(key, str) and key:
                        artifact_keys.append(key)
            keys_to_delete = [{"PK": item["PK"], "SK": item["SK"]} for item in items]
            deleted += await self._table.batch_delete(keys_to_delete)
            await best_effort_delete_keys(self._storage, artifact_keys)
        return deleted
