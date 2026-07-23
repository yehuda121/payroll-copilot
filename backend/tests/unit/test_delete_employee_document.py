"""Unit tests for scoped employee document delete."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from payroll_copilot.application.use_cases.delete_employee_document import (
    DeleteEmployeeDocumentUseCase,
    DocumentDeleteNotFoundError,
    DocumentDeleteScope,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


@dataclass
class _FakeDocs:
    items: dict = field(default_factory=dict)
    deleted: list = field(default_factory=list)

    async def get_by_id(self, document_id):
        return self.items.get(document_id)

    async def save(self, document):
        self.items[document.id] = document
        return document

    async def delete_by_ids(self, document_ids):
        for document_id in document_ids:
            self.items.pop(document_id, None)
            self.deleted.append(document_id)
        return len(document_ids)


@dataclass
class _FakeExtractions:
    by_doc: dict = field(default_factory=dict)
    deleted_for: list = field(default_factory=list)

    async def get_latest_for_document(self, document_id):
        return self.by_doc.get(document_id)

    async def delete_for_document_ids(self, document_ids):
        self.deleted_for.extend(document_ids)
        for document_id in document_ids:
            self.by_doc.pop(document_id, None)
        return len(document_ids)


@dataclass
class _FakeStorage:
    deleted: list = field(default_factory=list)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


def _doc(*, form_only: bool = False) -> Document:
    org = uuid4()
    emp = uuid4()
    return Document(
        id=uuid4(),
        document_type=DocumentType.NATIONAL_ID,
        storage_key="org/emp/file.pdf",
        original_filename="id.pdf",
        mime_type="application/pdf",
        file_size_bytes=1200,
        checksum_sha256="abc",
        status=DocumentStatus.UPLOADED,
        organization_id=org,
        employee_id=emp,
        metadata={"form_only": True} if form_only else {},
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_delete_both_removes_document_and_digital() -> None:
    document = _doc()
    docs = _FakeDocs(items={document.id: document})
    extractions = _FakeExtractions(
        by_doc={
            document.id: DocumentExtraction(
                id=uuid4(),
                document_id=document.id,
                engine="test",
                raw_text="",
                structured_data={},
            )
        }
    )
    storage = _FakeStorage()
    use_case = DeleteEmployeeDocumentUseCase(
        documents=docs,
        extractions=extractions,
        storage=storage,
    )
    result = await use_case.execute(
        document_id=document.id,
        organization_id=document.organization_id,
        employee_id=document.employee_id,
        scope=DocumentDeleteScope.BOTH,
    )
    assert result["deleted_original"] is True
    assert result["deleted_digital"] is True
    assert result["document_removed"] is True
    assert document.id not in docs.items
    assert document.id in extractions.deleted_for
    assert "org/emp/file.pdf" in storage.deleted


@pytest.mark.asyncio
async def test_delete_digital_keeps_original() -> None:
    document = _doc()
    docs = _FakeDocs(items={document.id: document})
    extractions = _FakeExtractions(
        by_doc={
            document.id: DocumentExtraction(
                id=uuid4(),
                document_id=document.id,
                engine="test",
                raw_text="",
                structured_data={},
            )
        }
    )
    storage = _FakeStorage()
    use_case = DeleteEmployeeDocumentUseCase(
        documents=docs,
        extractions=extractions,
        storage=storage,
    )
    result = await use_case.execute(
        document_id=document.id,
        organization_id=document.organization_id,
        employee_id=document.employee_id,
        scope=DocumentDeleteScope.DIGITAL,
    )
    assert result["deleted_digital"] is True
    assert result["document_removed"] is False
    assert document.id in docs.items
    assert docs.items[document.id].storage_key == "org/emp/file.pdf"
    assert storage.deleted == []


@pytest.mark.asyncio
async def test_delete_original_keeps_digital() -> None:
    document = _doc()
    docs = _FakeDocs(items={document.id: document})
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=document.id,
        engine="test",
        raw_text="",
        structured_data={"full_name": "A"},
    )
    extractions = _FakeExtractions(by_doc={document.id: extraction})
    storage = _FakeStorage()
    use_case = DeleteEmployeeDocumentUseCase(
        documents=docs,
        extractions=extractions,
        storage=storage,
    )
    result = await use_case.execute(
        document_id=document.id,
        organization_id=document.organization_id,
        employee_id=document.employee_id,
        scope=DocumentDeleteScope.ORIGINAL,
    )
    assert result["deleted_original"] is True
    assert result["document_removed"] is False
    cleared = docs.items[document.id]
    assert cleared.storage_key == ""
    assert cleared.metadata.get("original_removed") is True
    assert document.id in extractions.by_doc
    assert "org/emp/file.pdf" in storage.deleted


@pytest.mark.asyncio
async def test_delete_not_found() -> None:
    docs = _FakeDocs()
    use_case = DeleteEmployeeDocumentUseCase(
        documents=docs,
        extractions=_FakeExtractions(),
        storage=_FakeStorage(),
    )
    with pytest.raises(DocumentDeleteNotFoundError):
        await use_case.execute(
            document_id=uuid4(),
            organization_id=uuid4(),
            employee_id=uuid4(),
            scope=DocumentDeleteScope.BOTH,
        )
