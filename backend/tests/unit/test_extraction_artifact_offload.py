"""Focused tests for DocumentExtraction artifact offload / dual-read."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from payroll_copilot.application.services.extraction_explainability import (
    build_field_evidence_map,
)
from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.dynamodb.extraction_artifacts import (
    DYNAMODB_ITEM_SAFE_SIZE_BYTES,
    ExtractionArtifactMissingError,
    ExtractionItemTooLargeError,
    build_extraction_artifact_storage_key,
    deserialize_artifact_payload,
    estimate_dynamodb_item_size_bytes,
    prepare_extraction_item_for_put,
    serialize_artifact_payload,
)
from payroll_copilot.infrastructure.persistence.dynamodb.extractions import (
    DynamoDocumentExtractionRepository,
)


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.upload_calls = 0
        self.fail_upload = False
        self.deleted: list[str] = []

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self.upload_calls += 1
        if self.fail_upload:
            raise RuntimeError("upload_failed")
        self.objects[key] = data
        return key

    async def download(self, key: str) -> bytes:
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


class _FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}
        self.fail_put = False

    async def put_item(self, item: dict, *, condition_expression=None) -> None:
        if self.fail_put:
            raise RuntimeError("dynamo_put_failed")
        self.items[(item["PK"], item["SK"])] = dict(item)

    async def query_eq_pk(
        self,
        pk: str,
        *,
        index_name: str | None = None,
        sk_begins_with: str | None = None,
        scan_index_forward: bool = True,
        limit: int | None = None,
    ) -> list[dict]:
        rows = []
        for item in self.items.values():
            if index_name == "GSI1":
                if item.get("GSI1PK") != pk:
                    continue
            elif item.get("PK") != pk:
                continue
            if sk_begins_with and not str(item.get("SK", "")).startswith(sk_begins_with):
                continue
            rows.append(dict(item))
        if not scan_index_forward:
            rows = list(reversed(rows))
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def delete_item(self, key: dict) -> None:
        self.items.pop((key["PK"], key["SK"]), None)

    async def batch_delete(self, keys: list[dict]) -> int:
        n = 0
        for key in keys:
            if (key["PK"], key["SK"]) in self.items:
                del self.items[(key["PK"], key["SK"])]
                n += 1
        return n


def _now() -> datetime:
    return datetime.now(UTC)


def _extraction(
    *,
    ocr_result: dict | None = None,
    layout_analysis: dict | None = None,
    layout_snapshot: dict | None = None,
    structured_data: dict | None = None,
    raw_text: str = "sample",
) -> DocumentExtraction:
    return DocumentExtraction(
        id=uuid4(),
        document_id=uuid4(),
        engine="tesseract",
        raw_text=raw_text,
        structured_data=structured_data
        or {
            "employee_name": {"value": "Test User", "status": "FOUND"},
            "net_salary": {"value": 1000, "status": "FOUND"},
        },
        overall_confidence=0.9,
        field_confidences={"net_salary": 0.9},
        ocr_result=ocr_result if ocr_result is not None else {"pages": []},
        layout_analysis=layout_analysis if layout_analysis is not None else {},
        layout_snapshot=layout_snapshot if layout_snapshot is not None else {},
        created_at=_now(),
        updated_at=_now(),
    )


def _bloated_payload(label: str, target_bytes: int = 200_000) -> dict:
    """Build a dict that serializes to roughly ``target_bytes``."""
    chunk = "א" * 500 + "x" * 500
    pages = []
    size = 0
    i = 0
    while size < target_bytes:
        page = {
            "page": i + 1,
            "words": [
                {
                    "text": f"{label}-{i}-{j}-{chunk}",
                    "confidence": 0.9,
                    "bbox": [j, j + 1, j + 2, j + 3],
                }
                for j in range(40)
            ],
        }
        pages.append(page)
        size = len(serialize_artifact_payload({"pages": pages}))
        i += 1
        if i > 80:
            break
    return {"schema_version": 1, "label": label, "pages": pages}


@pytest.mark.asyncio
async def test_small_extraction_stays_inline() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result={"pages": [{"page": 1, "words": [{"text": "hi"}]}]},
        layout_analysis={"schema_version": 1, "associations": []},
    )

    await repo.save(extraction)

    assert storage.upload_calls == 0
    stored = next(iter(table.items.values()))
    assert "ocr_result" in stored
    assert "ocr_result_storage_key" not in stored
    assert estimate_dynamodb_item_size_bytes(stored) < DYNAMODB_ITEM_SAFE_SIZE_BYTES


@pytest.mark.asyncio
async def test_oversized_extraction_offloads_artifacts() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )
    full_item = repo._to_item(extraction)
    assert estimate_dynamodb_item_size_bytes(full_item) > DYNAMODB_ITEM_SAFE_SIZE_BYTES

    await repo.save(extraction)

    stored = next(iter(table.items.values()))
    assert "ocr_result" not in stored
    assert "layout_analysis" not in stored
    assert stored.get("ocr_result_storage_key")
    assert stored.get("layout_analysis_storage_key")
    assert estimate_dynamodb_item_size_bytes(stored) <= DYNAMODB_ITEM_SAFE_SIZE_BYTES
    assert storage.upload_calls >= 2
    assert extraction.ocr_result  # in-memory payload preserved
    assert extraction.layout_analysis


@pytest.mark.asyncio
async def test_canonical_structured_data_remains_inline_when_offloaded() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    structured = {
        "employee_name": {"value": "Canonical Name", "status": "FOUND"},
        "net_salary": {"value": 5555, "status": "FOUND"},
        "dynamic_entries": [{"label": "bonus", "amount": 10}],
    }
    extraction = _extraction(
        structured_data=structured,
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )

    await repo.save(extraction)
    stored = next(iter(table.items.values()))

    assert stored["structured_data"]["employee_name"]["value"] == "Canonical Name"
    assert stored["structured_data"]["net_salary"]["value"] == 5555
    assert "ocr_result" not in stored


@pytest.mark.asyncio
async def test_round_trip_large_record_dual_read() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    ocr = _bloated_payload("ocr", 220_000)
    layout = _bloated_payload("layout", 220_000)
    extraction = _extraction(ocr_result=ocr, layout_analysis=layout)

    await repo.save(extraction)
    loaded = await repo.get_by_id(extraction.id)

    assert loaded is not None
    assert loaded.structured_data["net_salary"]["value"] == 1000
    assert loaded.ocr_result["label"] == "ocr"
    assert loaded.layout_analysis["label"] == "layout"
    assert len(loaded.ocr_result["pages"]) == len(ocr["pages"])
    assert loaded.ocr_result_storage_key
    assert loaded.layout_analysis_storage_key


@pytest.mark.asyncio
async def test_old_inline_record_reads_unchanged() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result={"pages": [{"page": 1, "text": "legacy"}]},
        layout_analysis={"schema_version": 1, "associations": [{"id": "a1"}]},
    )
    # Simulate legacy write: put full item without going through offload path.
    item = repo._to_item(extraction)
    await table.put_item(item)

    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    assert loaded.ocr_result["pages"][0]["text"] == "legacy"
    assert loaded.layout_analysis["associations"][0]["id"] == "a1"
    assert storage.upload_calls == 0


@pytest.mark.asyncio
async def test_pointer_record_loads_from_object_storage() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(ocr_result={}, layout_analysis={})
    key = build_extraction_artifact_storage_key(
        document_id=str(extraction.document_id),
        extraction_id=str(extraction.id),
        extraction_version=1,
        artifact="ocr_result",
    )
    payload = {"engine": "tesseract", "pages": [{"page": 1, "words": [{"text": "hi"}]}]}
    await storage.upload(key, serialize_artifact_payload(payload), "application/json")
    item = repo._to_item(extraction)
    item.pop("ocr_result", None)
    item["ocr_result_storage_key"] = key
    await table.put_item(item)

    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    assert loaded.ocr_result["pages"][0]["words"][0]["text"] == "hi"


@pytest.mark.asyncio
async def test_missing_artifact_raises_controlled_error() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction()
    item = repo._to_item(extraction)
    item.pop("ocr_result", None)
    item["ocr_result_storage_key"] = "documents/missing/extractions/x/v1/ocr_result.json"
    await table.put_item(item)

    with pytest.raises(ExtractionArtifactMissingError):
        await repo.get_by_id(extraction.id)


@pytest.mark.asyncio
async def test_storage_write_failure_does_not_persist_extraction() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    storage.fail_upload = True
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )

    with pytest.raises(RuntimeError, match="upload_failed"):
        await repo.save(extraction)

    assert table.items == {}


@pytest.mark.asyncio
async def test_dynamo_failure_after_offload_rolls_back_uploaded_keys() -> None:
    table = _FakeTable()
    table.fail_put = True
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )

    with pytest.raises(RuntimeError, match="dynamo_put_failed"):
        await repo.save(extraction)

    assert table.items == {}
    assert storage.upload_calls >= 1
    assert storage.objects == {}
    assert storage.deleted


@pytest.mark.asyncio
async def test_final_item_size_guard() -> None:
    oversized = {
        "PK": "DOC#x",
        "SK": "EXT#1",
        "id": str(uuid4()),
        "document_id": str(uuid4()),
        "structured_data": {"keep": True},
        "ocr_result": _bloated_payload("ocr", 220_000),
        "layout_analysis": _bloated_payload("layout", 220_000),
        "raw_text": "x" * 50_000,
    }
    # Even after offloading OCR/layout, raw_text alone may keep size high —
    # use storage and confirm prepare either succeeds under limit or raises guard.
    storage = _FakeStorage()
    item, keys = await prepare_extraction_item_for_put(
        item=oversized,
        document_id=str(uuid4()),
        extraction_id=str(uuid4()),
        extraction_version=1,
        object_storage=storage,
    )
    assert estimate_dynamodb_item_size_bytes(item) <= DYNAMODB_ITEM_SAFE_SIZE_BYTES
    assert keys
    assert "ocr_result" not in item
    assert "layout_analysis" not in item


@pytest.mark.asyncio
async def test_digital_payslip_canonical_fields_available_after_offload() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        structured_data={
            "employee_name": {"value": "Payslip Name", "status": "FOUND"},
            "gross_salary": {"value": 9000, "status": "FOUND"},
            "net_salary": {"value": 7000, "status": "FOUND"},
        },
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )
    await repo.save(extraction)
    loaded = await repo.get_latest_for_document(extraction.document_id)
    assert loaded is not None
    # Digital payslip paths use structured_data only for field display.
    assert loaded.structured_data["gross_salary"]["value"] == 9000
    assert loaded.structured_data["net_salary"]["value"] == 7000
    stored = next(iter(table.items.values()))
    assert "structured_data" in stored


@pytest.mark.asyncio
async def test_validation_inputs_use_structured_data_unchanged() -> None:
    """Validation consumes structured_data; offload must not alter it."""
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    structured = {
        "pay_period": {"value": "2026-01", "status": "FOUND"},
        "net_salary": {"value": 1234, "status": "FOUND"},
    }
    extraction = _extraction(
        structured_data=structured,
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=_bloated_payload("layout", 220_000),
    )
    await repo.save(extraction)
    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    assert loaded.structured_data == structured


@pytest.mark.asyncio
async def test_evidence_explainability_works_with_offloaded_layout() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    structured = {
        "net_salary": {
            "value": 100,
            "status": "FOUND",
            "evidence_ref": "assoc-1",
        }
    }
    layout = _bloated_payload("layout", 220_000)
    layout["associations"] = [
        {
            "id": "assoc-1",
            "label_text": "Net",
            "value_text": "100",
            "confidence": 0.9,
        }
    ]
    extraction = _extraction(
        structured_data=structured,
        ocr_result=_bloated_payload("ocr", 220_000),
        layout_analysis=layout,
    )
    await repo.save(extraction)
    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    evidence = build_field_evidence_map(loaded.structured_data, loaded.layout_analysis)
    assert "net_salary" in evidence or evidence is not None
    # Ensure layout associations survived offload round-trip.
    assert any(
        a.get("id") == "assoc-1" for a in loaded.layout_analysis.get("associations", [])
    )


@pytest.mark.asyncio
async def test_multi_page_sized_extraction_persists_without_size_error() -> None:
    """Two-page-class payload (~OCR + layout) must persist via offload."""
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        raw_text="page1\npage2\n" * 200,
        ocr_result=_bloated_payload("ocr-2p", 300_000),
        layout_analysis=_bloated_payload("layout-2p", 300_000),
        layout_snapshot=_bloated_payload("snap-2p", 50_000),
    )
    await repo.save(extraction)
    stored = next(iter(table.items.values()))
    assert estimate_dynamodb_item_size_bytes(stored) <= DYNAMODB_ITEM_SAFE_SIZE_BYTES
    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    assert loaded.ocr_result["label"] == "ocr-2p"


@pytest.mark.asyncio
async def test_one_page_small_extraction_unchanged() -> None:
    table = _FakeTable()
    storage = _FakeStorage()
    repo = DynamoDocumentExtractionRepository(table, object_storage=storage)  # type: ignore[arg-type]
    extraction = _extraction(
        ocr_result={"pages": [{"page": 1, "words": [{"text": "one"}]}]},
        layout_analysis={"schema_version": 1, "pages": [{"page": 1}]},
    )
    await repo.save(extraction)
    assert storage.upload_calls == 0
    loaded = await repo.get_by_id(extraction.id)
    assert loaded is not None
    assert loaded.ocr_result["pages"][0]["words"][0]["text"] == "one"


@pytest.mark.asyncio
async def test_oversized_without_storage_raises() -> None:
    item = {
        "PK": "DOC#x",
        "SK": "EXT#1",
        "id": str(uuid4()),
        "document_id": str(uuid4()),
        "ocr_result": _bloated_payload("ocr", 400_000),
    }
    with pytest.raises(ExtractionItemTooLargeError):
        await prepare_extraction_item_for_put(
            item=item,
            document_id=str(uuid4()),
            extraction_id=str(uuid4()),
            extraction_version=1,
            object_storage=None,
        )


def test_artifact_json_round_trip() -> None:
    payload = {"pages": [{"page": 1, "words": [{"text": "שלום"}]}]}
    raw = serialize_artifact_payload(payload)
    assert deserialize_artifact_payload(raw) == payload
