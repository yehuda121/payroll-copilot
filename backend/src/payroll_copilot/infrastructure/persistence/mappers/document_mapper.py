"""Map between domain documents and SQLAlchemy models."""

from __future__ import annotations

from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.persistence.models import DocumentModel


def document_to_entity(model: DocumentModel) -> Document:
    period = None
    if model.period_year is not None and model.period_month is not None:
        period = PayPeriod(year=model.period_year, month=model.period_month)

    return Document(
        id=model.id,
        document_type=model.document_type,
        storage_key=model.storage_key,
        original_filename=model.original_filename,
        mime_type=model.mime_type,
        file_size_bytes=model.file_size_bytes,
        checksum_sha256=model.checksum_sha256,
        status=model.status,
        organization_id=model.organization_id,
        uploaded_by=model.uploaded_by,
        employee_id=model.employee_id,
        period=period,
        metadata=model.metadata_,
        created_at=model.created_at,
        expires_at=model.expires_at,
    )


def document_to_model(document: Document) -> DocumentModel:
    period_year = document.period.year if document.period else None
    period_month = document.period.month if document.period else None

    return DocumentModel(
        id=document.id,
        organization_id=document.organization_id,
        uploaded_by=document.uploaded_by,
        document_type=document.document_type,
        storage_key=document.storage_key,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        file_size_bytes=document.file_size_bytes,
        checksum_sha256=document.checksum_sha256,
        status=document.status,
        employee_id=document.employee_id,
        period_year=period_year,
        period_month=period_month,
        metadata_=document.metadata,
        created_at=document.created_at,
        expires_at=document.expires_at,
    )
