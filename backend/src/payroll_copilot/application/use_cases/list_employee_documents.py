"""List authenticated employee documents for the Employee Document Center."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    LIFECYCLE_EXTRACTION_COMPLETED,
    LIFECYCLE_REVIEW_REQUIRED,
    LIFECYCLE_UPLOADED,
    PERSISTENT_TYPES,
    is_employee_visible_document,
)
from payroll_copilot.domain.enums import DocumentType


def _extraction_connection(document_type: DocumentType) -> str:
    if document_type == DocumentType.PAYSLIP or document_type in PERSISTENT_TYPES:
        return "connected"
    return "extraction_not_connected"


def _has_original_file(doc: Any) -> bool:
    meta = dict(getattr(doc, "metadata", None) or {})
    if meta.get("form_only") or meta.get("original_removed"):
        return False
    storage_key = str(getattr(doc, "storage_key", "") or "")
    file_size = int(getattr(doc, "file_size_bytes", 0) or 0)
    return bool(storage_key) and file_size > 0


def _doc_row(
    *,
    document_type: DocumentType,
    doc: Any | None,
    extraction: Any | None,
    version_count: int,
) -> dict[str, Any]:
    dtype = document_type.value
    if doc is None:
        return {
            "document_type": dtype,
            "exists": False,
            "has_original_file": False,
            "document_id": None,
            "original_filename": None,
            "uploaded_at": None,
            "processing_status": "missing",
            "extraction_status": "missing",
            "confirmation_status": "missing",
            "lifecycle_status": "missing",
            "extraction_connection": _extraction_connection(document_type),
            "version_count": 0,
            "payroll_year": None,
            "payroll_month": None,
            "actions": {
                "can_upload": True,
                "can_replace": False,
                "can_review": False,
                "can_confirm": False,
            },
        }

    meta = dict(doc.metadata or {})
    has_original = _has_original_file(doc)
    confirmation = (
        (extraction.confirmation_status if extraction else None)
        or meta.get("lifecycle_status")
        or "review_required"
    )
    extraction_status = meta.get("extraction_status")
    if extraction is not None:
        extraction_status = extraction_status or LIFECYCLE_EXTRACTION_COMPLETED
    elif _extraction_connection(document_type) != "connected":
        extraction_status = extraction_status or "extraction_not_connected"
    else:
        extraction_status = extraction_status or LIFECYCLE_UPLOADED

    lifecycle = meta.get("lifecycle_status") or (
        confirmation if confirmation == "confirmed" else LIFECYCLE_REVIEW_REQUIRED
        if extraction
        else LIFECYCLE_UPLOADED
    )

    return {
        "document_type": dtype,
        # exists = original file present (upload replace UX). document_id remains when
        # digital-only residual rows exist after scoped original delete.
        "exists": has_original,
        "has_original_file": has_original,
        "document_id": str(doc.id),
        "original_filename": doc.original_filename if has_original else None,
        "uploaded_at": doc.created_at.isoformat() if has_original and doc.created_at else None,
        "processing_status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        "extraction_status": extraction_status if extraction is not None else "missing",
        "confirmation_status": confirmation if extraction else "missing",
        "lifecycle_status": lifecycle if (has_original or extraction) else "missing",
        "extraction_connection": _extraction_connection(document_type),
        "version_count": version_count,
        "payroll_year": doc.period.year if doc.period else None,
        "payroll_month": doc.period.month if doc.period else None,
        "actions": {
            "can_upload": True,
            "can_replace": has_original,
            "can_review": document_type == DocumentType.PAYSLIP
            or document_type in PERSISTENT_TYPES,
            "can_confirm": document_type == DocumentType.PAYSLIP and confirmation != "confirmed",
        },
    }


class ListEmployeeDocumentsUseCase:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions

    async def execute(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        include_unpublished: bool = False,
    ) -> dict[str, Any]:
        docs = await self._documents.list_for_employee(
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if not include_unpublished:
            docs = [doc for doc in docs if is_employee_visible_document(doc)]

        by_type: dict[DocumentType, list[Any]] = {t: [] for t in PERSISTENT_TYPES}
        monthly_count = 0
        for doc in docs:
            if doc.document_type in PERSISTENT_TYPES:
                by_type[doc.document_type].append(doc)
            elif doc.document_type in {DocumentType.PAYSLIP, DocumentType.ATTENDANCE}:
                monthly_count += 1

        persistent: list[dict[str, Any]] = []
        for dtype in (
            DocumentType.NATIONAL_ID,
            DocumentType.ID_APPENDIX,
            DocumentType.CONTRACT,
        ):
            versions = sorted(
                by_type.get(dtype, []),
                key=lambda d: d.created_at or d.id,
                reverse=True,
            )
            latest = versions[0] if versions else None
            extraction = None
            if latest is not None and self._extractions is not None:
                extraction = await self._extractions.get_latest_for_document(latest.id)
            persistent.append(
                _doc_row(
                    document_type=dtype,
                    doc=latest,
                    extraction=extraction,
                    version_count=len(versions),
                )
            )

        return {
            "persistent_documents": persistent,
            "monthly_documents": {
                "count": monthly_count,
                "access_path": "payroll-months",
                "note_code": "use_payroll_months",
            },
            "national_id_review": {
                "extraction_connection": "connected",
                "parser_status": "document_workspace",
            },
        }
