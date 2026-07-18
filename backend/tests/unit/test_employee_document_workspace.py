from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from payroll_copilot.application.services.dynamic_document import new_entry
from payroll_copilot.application.use_cases.employee_document_workspace import (
    EmployeeDocumentWorkspaceUseCase,
    ExtractEmployeeDocumentCommand,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


class _Documents:
    def __init__(self, old_document: Document, events: list[str]) -> None:
        self.items = {old_document.id: old_document}
        self.events = events

    async def get_by_id(self, document_id):
        return self.items.get(document_id)

    async def list_for_employee(self, **_kwargs):
        return list(self.items.values())

    async def save(self, document):
        self.items[document.id] = document
        if document.status == DocumentStatus.PROCESSED:
            self.events.append("new_document_persisted")
        return document

    async def delete_by_ids(self, document_ids):
        for document_id in document_ids:
            self.items.pop(document_id, None)
        return len(document_ids)


class _Extractions:
    def __init__(self, events: list[str]) -> None:
        self.items = {}
        self.events = events

    async def get_by_id(self, extraction_id):
        return self.items.get(extraction_id)

    async def get_latest_for_document(self, document_id):
        matches = [item for item in self.items.values() if item.document_id == document_id]
        return max(matches, key=lambda item: item.extraction_version) if matches else None

    async def save(self, extraction):
        self.items[extraction.id] = extraction
        self.events.append("new_extraction_persisted")
        return extraction

    async def delete_for_document_ids(self, document_ids):
        doomed = [
            extraction_id
            for extraction_id, item in self.items.items()
            if item.document_id in document_ids
        ]
        for extraction_id in doomed:
            del self.items[extraction_id]
        return len(doomed)


class _Storage:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def upload(self, *_args):
        return "new-key"

    async def delete(self, key):
        self.events.append(f"delete:{key}")


class _Upload:
    def __init__(self, documents: _Documents) -> None:
        self.documents = documents

    async def execute(self, command):
        document = Document(
            id=uuid4(),
            document_type=command.document_type,
            storage_key="new-key",
            original_filename=command.original_filename,
            mime_type=command.mime_type,
            file_size_bytes=len(command.content),
            checksum_sha256="new",
            organization_id=command.organization_id,
            employee_id=command.employee_id,
            uploaded_by=command.uploaded_by_user_id,
        )
        return await self.documents.save(document)


class _Ocr:
    async def execute(self, _command):
        return SimpleNamespace(
            raw_text="Name: Example\nID: 313366783\n25.11.1994",
            pages=[SimpleNamespace(text="Name: Example\nID: 313366783\n25.11.1994")],
            language_effective="en",
            engine="test-ocr",
            overall_confidence=0.9,
            warnings=[],
        )


class _Extractor:
    async def extract(self, **_kwargs):
        return [new_entry(key="Name", value="Example", confidence=0.9)], "test-model", []


class _FixedExtractor:
    async def extract(self, **_kwargs):
        structured = {
            "additional_fields": {
                "full_name": {
                    "value": "Example",
                    "confidence": 0.9,
                    "source_text": "Name: Example",
                    "status": "FOUND",
                    "edited_by_user": False,
                    "original_value": "Example",
                },
                "national_id": {
                    "value": "313366783",
                    "confidence": 0.9,
                    "source_text": None,
                    "status": "FOUND",
                    "edited_by_user": False,
                    "original_value": "313366783",
                },
                "birth_date": {
                    "value": "25.11.1994",
                    "confidence": 0.9,
                    "source_text": None,
                    "status": "FOUND",
                    "edited_by_user": False,
                    "original_value": "25.11.1994",
                },
            }
        }
        return structured, "test-fixed-model", []


class _FailingExtractor:
    async def extract(self, **_kwargs):
        raise RuntimeError("extraction failed")


@pytest.mark.asyncio
async def test_replacement_deletes_old_object_only_after_new_form_is_persisted():
    events: list[str] = []
    organization_id = uuid4()
    employee_id = uuid4()
    old_document = Document(
        id=uuid4(),
        document_type=DocumentType.NATIONAL_ID,
        storage_key="old-key",
        original_filename="old.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="old",
        status=DocumentStatus.PROCESSED,
        organization_id=organization_id,
        employee_id=employee_id,
        created_at=datetime.now(UTC),
    )
    documents = _Documents(old_document, events)
    extractions = _Extractions(events)
    storage = _Storage(events)
    use_case = EmployeeDocumentWorkspaceUseCase(
        documents=documents,
        extractions=extractions,
        storage=storage,
        upload_document=_Upload(documents),
        ocr=_Ocr(),
        extractor=_Extractor(),
        fixed_extractor=_FixedExtractor(),
    )

    result = await use_case.extract_and_replace(
        ExtractEmployeeDocumentCommand(
            content=b"%PDF test",
            original_filename="new.pdf",
            mime_type="application/pdf",
            language="en",
            document_type=DocumentType.NATIONAL_ID,
            organization_id=organization_id,
            employee_id=employee_id,
            user_id=uuid4(),
        )
    )

    assert result.document.id in documents.items
    assert old_document.id not in documents.items
    assert events.index("new_extraction_persisted") < events.index("delete:old-key")
    assert events.index("new_document_persisted") < events.index("delete:old-key")


@pytest.mark.asyncio
async def test_failed_replacement_keeps_previous_document_and_object():
    events: list[str] = []
    organization_id = uuid4()
    employee_id = uuid4()
    old_document = Document(
        id=uuid4(),
        document_type=DocumentType.CONTRACT,
        storage_key="old-contract-key",
        original_filename="old.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="old",
        status=DocumentStatus.PROCESSED,
        organization_id=organization_id,
        employee_id=employee_id,
    )
    documents = _Documents(old_document, events)
    storage = _Storage(events)
    use_case = EmployeeDocumentWorkspaceUseCase(
        documents=documents,
        extractions=_Extractions(events),
        storage=storage,
        upload_document=_Upload(documents),
        ocr=_Ocr(),
        extractor=_FailingExtractor(),
    )

    with pytest.raises(RuntimeError, match="extraction failed"):
        await use_case.extract_and_replace(
            ExtractEmployeeDocumentCommand(
                content=b"%PDF test",
                original_filename="new.pdf",
                mime_type="application/pdf",
                language="en",
                document_type=DocumentType.CONTRACT,
                organization_id=organization_id,
                employee_id=employee_id,
                user_id=uuid4(),
            )
        )

    assert documents.items == {old_document.id: old_document}
    assert "delete:old-contract-key" not in events
