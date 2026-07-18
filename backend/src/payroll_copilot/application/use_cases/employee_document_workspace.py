"""Employee Documents extraction, persisted editing, and safe replacement."""

from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from payroll_copilot.application.exceptions import (
    DocumentNotFoundError,
    DocumentNotOwnedError,
    PayslipParserSemanticError,
)
from payroll_copilot.application.services.dynamic_document import entries_have_usable_values
from payroll_copilot.application.services.employee_document_form_schemas import (
    empty_fixed_structured,
    fixed_keys_for,
    project_fixed_structured,
    structured_from_fixed_fields,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    LIFECYCLE_REVIEW_REQUIRED,
    LIFECYCLE_UPLOADED,
    PERSISTENT_TYPES,
    build_employee_storage_key,
    fields_from_structured,
)
from payroll_copilot.application.services.employee_dynamic_document_extractor import (
    EmployeeDynamicDocumentExtractor,
)
from payroll_copilot.application.services.employee_fixed_document_extractor import (
    EmployeeFixedDocumentExtractor,
    fixed_structured_has_usable_values,
)
from payroll_copilot.application.use_cases.documents import (
    UploadDocumentCommand,
)
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType
from payroll_copilot.infrastructure.ocr.text_normalize import normalize_extracted_text

if TYPE_CHECKING:
    from uuid import UUID

    from payroll_copilot.application.ports.object_storage import ObjectStoragePort
    from payroll_copilot.application.ports.repositories import (
        DocumentExtractionRepository,
        DocumentRepository,
    )
    from payroll_copilot.application.use_cases.documents import UploadDocumentUseCase
    from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractEmployeeDocumentCommand:
    content: bytes
    original_filename: str
    mime_type: str
    language: str
    document_type: DocumentType
    organization_id: UUID
    employee_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class EmployeeDocumentFormResult:
    document: Document
    extraction: DocumentExtraction
    fields: list[dict[str, Any]]


def _structured_from_entries(entries: list[Any]) -> tuple[dict[str, Any], dict[str, float]]:
    """Persist dynamic extractor output for Employment Contract (unchanged path)."""
    additional: dict[str, Any] = {}
    confidences: dict[str, float] = {}
    used: dict[str, int] = {}
    for index, entry in enumerate(entries, start=1):
        base = str(entry.key or "").strip() or f"field_{index}"
        used[base] = used.get(base, 0) + 1
        key = base if used[base] == 1 else f"{base} ({used[base]})"
        status = "FOUND" if entry.value not in (None, "") else "MISSING"
        additional[key] = {
            "value": entry.value,
            "confidence": entry.confidence if status == "FOUND" else None,
            "source_text": entry.source_text,
            "status": status,
            "edited_by_user": False,
            "original_value": entry.value,
        }
        if entry.confidence is not None and status == "FOUND":
            confidences[key] = float(entry.confidence)
    return {"additional_fields": additional}, confidences


def _confidences_from_fixed(structured: dict[str, Any]) -> dict[str, float]:
    additional = structured.get("additional_fields")
    if not isinstance(additional, dict):
        return {}
    return {
        key: float(payload["confidence"])
        for key, payload in additional.items()
        if isinstance(payload, dict) and payload.get("confidence") is not None
    }


def _fields_for_response(
    document_type: DocumentType,
    structured: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    projected = (
        project_fixed_structured(document_type, structured)
        if fixed_keys_for(document_type) is not None
        else (structured or {})
    )
    return fields_from_structured(projected)


class EmployeeDocumentWorkspaceUseCase:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        storage: ObjectStoragePort,
        upload_document: UploadDocumentUseCase,
        ocr: ExtractDocumentTextUseCase,
        extractor: EmployeeDynamicDocumentExtractor | None = None,
        fixed_extractor: EmployeeFixedDocumentExtractor | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._storage = storage
        self._upload_document = upload_document
        self._ocr = ocr
        self._extractor = extractor or EmployeeDynamicDocumentExtractor()
        self._fixed_extractor = fixed_extractor or EmployeeFixedDocumentExtractor()

    async def extract_and_replace(
        self,
        command: ExtractEmployeeDocumentCommand,
    ) -> EmployeeDocumentFormResult:
        if command.document_type not in PERSISTENT_TYPES:
            raise ValueError("Unsupported Employee Documents type.")

        # Run OCR + AI before changing the currently active document.
        ocr_result = await self._ocr.execute(
            ExtractDocumentTextCommand(
                content=command.content,
                filename=command.original_filename,
                content_type=command.mime_type,
                language=command.language,
            )
        )
        raw_text = normalize_extracted_text(ocr_result.raw_text)
        language = ocr_result.language_effective or command.language
        pages_text = [page.text for page in ocr_result.pages]
        if fixed_keys_for(command.document_type) is not None:
            structured, model_name, warnings = await self._fixed_extractor.extract(
                ocr_text=raw_text,
                language=language,
                document_type=command.document_type,
                pages_text=pages_text,
            )
            if not fixed_structured_has_usable_values(structured):
                raise PayslipParserSemanticError(
                    "We could not extract usable information from this document.",
                    warning_code="fixed_document_extractor_no_usable_entries",
                )
            confidences = _confidences_from_fixed(structured)
        else:
            entries, model_name, warnings = await self._extractor.extract(
                ocr_text=raw_text,
                language=language,
                document_type=command.document_type.value,
                pages_text=pages_text,
            )
            if not entries_have_usable_values(entries):
                raise PayslipParserSemanticError(
                    "We could not extract usable information from this document.",
                    warning_code="document_extractor_no_usable_entries",
                )
            structured, confidences = _structured_from_entries(entries)

        old_documents = [
            document
            for document in await self._documents.list_for_employee(
                organization_id=command.organization_id,
                employee_id=command.employee_id,
            )
            if document.document_type == command.document_type
        ]

        new_document: Document | None = None
        try:
            new_document = await self._upload_document.execute(
                UploadDocumentCommand(
                    content=command.content,
                    original_filename=command.original_filename,
                    mime_type=command.mime_type,
                    document_type=command.document_type,
                    employee_id=command.employee_id,
                    organization_id=command.organization_id,
                    uploaded_by_user_id=command.user_id,
                    document_language=command.language,
                )
            )
            now = datetime.now(UTC)
            extraction = DocumentExtraction(
                id=uuid4(),
                document_id=new_document.id,
                engine=ocr_result.engine or "unknown",
                raw_text=raw_text,
                structured_data=structured,
                overall_confidence=ocr_result.overall_confidence,
                field_confidences=confidences,
                extraction_version=1,
                created_at=now,
                ocr_result={"warnings": list(ocr_result.warnings)},
                parser_model=model_name,
                language=ocr_result.language_effective or command.language,
                ocr_status="completed",
                parser_status="completed",
                warnings=list(dict.fromkeys([*ocr_result.warnings, *warnings])),
                updated_at=now,
                confirmation_status="review_required",
            )
            await self._extractions.save(extraction)

            metadata = dict(new_document.metadata or {})
            metadata.update(
                {
                    "lifecycle_status": LIFECYCLE_REVIEW_REQUIRED,
                    "extraction_status": "extraction_completed",
                    "extraction_connected": True,
                    "current_extraction_id": str(extraction.id),
                    "current_extraction_version": extraction.extraction_version,
                }
            )
            new_document.metadata = metadata
            new_document.status = DocumentStatus.PROCESSED
            await self._documents.save(new_document)
        except Exception:
            # Compensate any partially persisted replacement; old state remains untouched.
            if new_document is not None:
                try:
                    await self._extractions.delete_for_document_ids([new_document.id])
                    await self._documents.delete_by_ids([new_document.id])
                    await self._storage.delete(new_document.storage_key)
                except Exception:
                    logger.exception(
                        "Failed to clean up incomplete replacement document %s",
                        new_document.id,
                    )
            raise

        # New object + metadata + extraction are durable. Only now retire previous versions.
        for old_document in old_documents:
            try:
                await self._storage.delete(old_document.storage_key)
            except Exception:
                logger.exception(
                    "New document %s is active, but old S3 object %s could not be deleted",
                    new_document.id,
                    old_document.id,
                )
                continue
            await self._extractions.delete_for_document_ids([old_document.id])
            await self._documents.delete_by_ids([old_document.id])

        return EmployeeDocumentFormResult(
            document=new_document,
            extraction=extraction,
            fields=_fields_for_response(command.document_type, structured),
        )

    async def get_form(
        self,
        *,
        document_id: UUID,
        organization_id: UUID,
        employee_id: UUID,
    ) -> EmployeeDocumentFormResult:
        document = await self._owned_document(
            document_id=document_id,
            organization_id=organization_id,
            employee_id=employee_id,
        )
        extraction = await self._extractions.get_latest_for_document(document.id)
        if extraction is None:
            if fixed_keys_for(document.document_type) is None:
                raise DocumentNotFoundError(document.id)
            structured = empty_fixed_structured(document.document_type)
            now = datetime.now(UTC)
            extraction = DocumentExtraction(
                id=uuid4(),
                document_id=document.id,
                engine="manual",
                raw_text="",
                structured_data=structured,
                extraction_version=1,
                created_at=now,
                updated_at=now,
                confirmation_status="review_required",
                ocr_status="skipped",
                parser_status="manual",
            )
            return EmployeeDocumentFormResult(
                document=document,
                extraction=extraction,
                fields=_fields_for_response(document.document_type, structured),
            )
        return EmployeeDocumentFormResult(
            document=document,
            extraction=extraction,
            fields=_fields_for_response(document.document_type, extraction.structured_data),
        )

    async def get_form_by_type(
        self,
        *,
        document_type: DocumentType,
        organization_id: UUID,
        employee_id: UUID,
    ) -> EmployeeDocumentFormResult | None:
        document = await self._latest_document(
            document_type=document_type,
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if document is None:
            return None
        return await self.get_form(
            document_id=document.id,
            organization_id=organization_id,
            employee_id=employee_id,
        )

    async def save_form(
        self,
        *,
        document_id: UUID | None,
        document_type: DocumentType | None = None,
        organization_id: UUID,
        employee_id: UUID,
        user_id: UUID,
        fields: list[dict[str, Any]],
    ) -> EmployeeDocumentFormResult:
        document: Document | None = None
        if document_id is not None:
            document = await self._owned_document(
                document_id=document_id,
                organization_id=organization_id,
                employee_id=employee_id,
            )
        elif document_type is not None:
            document = await self._latest_document(
                document_type=document_type,
                organization_id=organization_id,
                employee_id=employee_id,
            )
            if document is None:
                if fixed_keys_for(document_type) is None:
                    raise DocumentNotFoundError(uuid4())
                document = await self._create_form_only_document(
                    document_type=document_type,
                    organization_id=organization_id,
                    employee_id=employee_id,
                    user_id=user_id,
                )
        else:
            raise ValueError("document_id or document_type is required")

        previous = await self._extractions.get_latest_for_document(document.id)
        structured = structured_from_fixed_fields(document.document_type, fields)
        now = datetime.now(UTC)
        version = (previous.extraction_version + 1) if previous else 1
        extraction = DocumentExtraction(
            id=uuid4(),
            document_id=document.id,
            engine=(previous.engine if previous else "manual"),
            raw_text=(previous.raw_text if previous else ""),
            structured_data=structured,
            overall_confidence=(previous.overall_confidence if previous else None),
            field_confidences={},
            extraction_version=version,
            created_at=now,
            ocr_result=deepcopy(previous.ocr_result) if previous else {},
            layout_snapshot=deepcopy(previous.layout_snapshot) if previous else {},
            layout_analysis=deepcopy(previous.layout_analysis) if previous else {},
            parser_model=(previous.parser_model if previous else None),
            language=(previous.language if previous else "he"),
            ocr_status=(previous.ocr_status if previous else "skipped"),
            parser_status=(previous.parser_status if previous else "manual"),
            warnings=list(
                dict.fromkeys(
                    [*(previous.warnings if previous else []), "Employee edited digital form."]
                )
            ),
            updated_at=now,
            confirmation_status="review_required",
            confirmed_by=user_id,
        )
        await self._extractions.save(extraction)
        metadata = dict(document.metadata or {})
        metadata.update(
            {
                "lifecycle_status": LIFECYCLE_REVIEW_REQUIRED,
                "extraction_status": "extraction_completed",
                "extraction_connected": True,
                "current_extraction_id": str(extraction.id),
                "current_extraction_version": extraction.extraction_version,
            }
        )
        document.metadata = metadata
        await self._documents.save(document)
        return EmployeeDocumentFormResult(
            document=document,
            extraction=extraction,
            fields=_fields_for_response(document.document_type, structured),
        )

    async def _create_form_only_document(
        self,
        *,
        document_type: DocumentType,
        organization_id: UUID,
        employee_id: UUID,
        user_id: UUID,
    ) -> Document:
        """Persist a Digital Form shell without requiring an uploaded original file."""
        document_id = uuid4()
        content = b'{"form_only":true}'
        storage_key = build_employee_storage_key(
            organization_id=organization_id,
            employee_id=employee_id,
            document_type=document_type,
            document_id=document_id,
            filename="digital-form.json",
        )
        await self._storage.upload(storage_key, content, "application/json")
        document = Document(
            id=document_id,
            document_type=document_type,
            storage_key=storage_key,
            original_filename="digital-form.json",
            mime_type="application/json",
            file_size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            status=DocumentStatus.UPLOADED,
            organization_id=organization_id,
            uploaded_by=user_id,
            employee_id=employee_id,
            metadata={
                "document_language": "he",
                "lifecycle_status": LIFECYCLE_UPLOADED,
                "extraction_status": "missing",
                "form_only": True,
                "storage_provider": "s3_compatible",
            },
        )
        return await self._documents.save(document)

    async def _latest_document(
        self,
        *,
        document_type: DocumentType,
        organization_id: UUID,
        employee_id: UUID,
    ) -> Document | None:
        documents = [
            document
            for document in await self._documents.list_for_employee(
                organization_id=organization_id,
                employee_id=employee_id,
            )
            if document.document_type == document_type
        ]
        if not documents:
            return None
        return sorted(documents, key=lambda item: item.created_at or item.id, reverse=True)[0]

    async def _owned_document(
        self,
        *,
        document_id: UUID,
        organization_id: UUID,
        employee_id: UUID,
    ) -> Document:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if (
            document.organization_id != organization_id
            or document.employee_id != employee_id
        ):
            raise DocumentNotOwnedError(document_id)
        if document.document_type not in PERSISTENT_TYPES:
            raise DocumentNotFoundError(document_id)
        return document
