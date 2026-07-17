"""Guest ephemeral session store — no permanent S3/DB for public landing flow."""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class GuestEphemeralSupportingDoc:
    """Temporary supporting document (ID / contract) for guest validation scope."""

    document_id: UUID
    document_type: DocumentType
    content: bytes
    original_filename: str
    mime_type: str
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at


@dataclass
class GuestEphemeralSession:
    document_id: UUID
    extraction_id: UUID
    content: bytes
    original_filename: str
    mime_type: str
    language: str
    ocr_status: str
    parser_status: str
    ocr_engine: str | None
    parser_model: str | None
    raw_text: str
    structured_data: dict[str, Any]
    ocr_result: dict[str, Any]
    warnings: list[str]
    error_message: str | None
    field_confidences: dict[str, float]
    dynamic_entries: list[dict[str, Any]] = field(default_factory=list)
    confirmation_status: str = "review_required"
    confirmed_at: datetime | None = None
    supporting_document_ids: list[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at


class GuestEphemeralStore:
    """Process-local TTL store for all guest landing documents and extractions."""

    def __init__(self, *, ttl_hours: float = 1.0) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._sessions: dict[UUID, GuestEphemeralSession] = {}
        self._supporting: dict[UUID, GuestEphemeralSupportingDoc] = {}
        self._lock = threading.RLock()

    def _purge_expired(self) -> None:
        expired_sessions = [key for key, session in self._sessions.items() if session.is_expired()]
        for key in expired_sessions:
            session = self._sessions.pop(key, None)
            if session is not None:
                for sid in session.supporting_document_ids:
                    self._supporting.pop(sid, None)
        expired_support = [key for key, doc in self._supporting.items() if doc.is_expired()]
        for key in expired_support:
            self._supporting.pop(key, None)

    def save(self, session: GuestEphemeralSession) -> GuestEphemeralSession:
        with self._lock:
            self._purge_expired()
            if session.expires_at is None:
                session.expires_at = _utcnow() + self._ttl
            self._sessions[session.document_id] = session
            return session

    def get(self, document_id: UUID) -> GuestEphemeralSession | None:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(document_id)
            if session is None or session.is_expired():
                self._sessions.pop(document_id, None)
                return None
            return session

    def delete(self, document_id: UUID) -> None:
        with self._lock:
            session = self._sessions.pop(document_id, None)
            if session is not None:
                for sid in session.supporting_document_ids:
                    self._supporting.pop(sid, None)

    def update_structured(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None:
        with self._lock:
            session = self.get(document_id)
            if session is None:
                return None
            session.structured_data = structured_data
            if extraction_id is not None:
                session.extraction_id = extraction_id
            if warnings is not None:
                session.warnings = list(dict.fromkeys([*session.warnings, *warnings]))
            return session

    def update_dynamic_entries(
        self,
        document_id: UUID,
        *,
        dynamic_entries: list[dict[str, Any]],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None:
        with self._lock:
            session = self.get(document_id)
            if session is None:
                return None
            session.dynamic_entries = list(dynamic_entries)
            if extraction_id is not None:
                session.extraction_id = extraction_id
            if warnings is not None:
                session.warnings = list(dict.fromkeys([*session.warnings, *warnings]))
            return session

    def confirm(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any] | None = None,
        dynamic_entries: list[dict[str, Any]] | None = None,
    ) -> GuestEphemeralSession | None:
        """Freeze effective fields for validation. Does not write S3/DB."""
        with self._lock:
            session = self.get(document_id)
            if session is None:
                return None
            if dynamic_entries is not None:
                session.dynamic_entries = list(dynamic_entries)
            if structured_data is not None:
                session.structured_data = deepcopy(structured_data)
            session.confirmation_status = "confirmed"
            session.confirmed_at = _utcnow()
            return session

    def save_supporting(
        self,
        *,
        document_type: DocumentType,
        content: bytes,
        original_filename: str,
        mime_type: str,
        payslip_document_id: UUID | None = None,
    ) -> GuestEphemeralSupportingDoc:
        with self._lock:
            self._purge_expired()
            doc = GuestEphemeralSupportingDoc(
                document_id=uuid4(),
                document_type=document_type,
                content=content,
                original_filename=original_filename,
                mime_type=mime_type,
                expires_at=_utcnow() + self._ttl,
            )
            self._supporting[doc.document_id] = doc
            if payslip_document_id is not None:
                session = self.get(payslip_document_id)
                if session is not None and doc.document_id not in session.supporting_document_ids:
                    session.supporting_document_ids.append(doc.document_id)
            return doc

    def get_supporting(self, document_id: UUID) -> GuestEphemeralSupportingDoc | None:
        with self._lock:
            self._purge_expired()
            doc = self._supporting.get(document_id)
            if doc is None or doc.is_expired():
                self._supporting.pop(document_id, None)
                return None
            return doc

    def build_document(self, session: GuestEphemeralSession) -> Document:
        from payroll_copilot.application.validation.demo_validation_context_builder import (
            DEMO_ORGANIZATION_ID,
        )

        return Document(
            id=session.document_id,
            document_type=DocumentType.PAYSLIP,
            storage_key=f"guest-temp/{session.document_id}",
            original_filename=session.original_filename,
            mime_type=session.mime_type,
            file_size_bytes=len(session.content),
            checksum_sha256="",
            status=DocumentStatus.PROCESSED
            if session.parser_status == "completed"
            else DocumentStatus.FAILED,
            organization_id=DEMO_ORGANIZATION_ID,
            metadata={
                "document_language": session.language,
                "guest_ephemeral": True,
                "lifecycle_status": session.confirmation_status,
                "confirmation_status": session.confirmation_status,
            },
            created_at=session.created_at,
        )

    def build_supporting_document(self, doc: GuestEphemeralSupportingDoc) -> Document:
        from payroll_copilot.application.validation.demo_validation_context_builder import (
            DEMO_ORGANIZATION_ID,
        )

        return Document(
            id=doc.document_id,
            document_type=doc.document_type,
            storage_key=f"guest-temp/{doc.document_id}",
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size_bytes=len(doc.content),
            checksum_sha256="",
            status=DocumentStatus.UPLOADED,
            organization_id=DEMO_ORGANIZATION_ID,
            metadata={"guest_ephemeral": True},
            created_at=doc.created_at,
        )

    def build_extraction(self, session: GuestEphemeralSession) -> DocumentExtraction:
        return DocumentExtraction(
            id=session.extraction_id,
            document_id=session.document_id,
            engine=session.ocr_engine or "unknown",
            raw_text=session.raw_text,
            structured_data=session.structured_data,
            overall_confidence=None,
            field_confidences=session.field_confidences,
            extraction_version=1,
            created_at=session.created_at,
            ocr_result=session.ocr_result,
            parser_model=session.parser_model,
            language=session.language,
            ocr_status=session.ocr_status,
            parser_status=session.parser_status,
            warnings=list(session.warnings),
            error_message=session.error_message,
            updated_at=_utcnow(),
            confirmation_status=session.confirmation_status,
            confirmed_at=session.confirmed_at,
        )

    def new_ids(self) -> tuple[UUID, UUID]:
        return uuid4(), uuid4()


_guest_store: GuestEphemeralStore | None = None


def get_guest_ephemeral_store(*, ttl_hours: float = 1.0) -> GuestEphemeralStore:
    global _guest_store
    if _guest_store is None:
        _guest_store = GuestEphemeralStore(ttl_hours=ttl_hours)
    return _guest_store


def reset_guest_ephemeral_store_for_tests() -> None:
    """Clear the process-local guest store (tests only)."""
    global _guest_store
    _guest_store = None
