"""Guest ephemeral session store — shared Redis (with in-memory fallback for tests/local).

Guest landing APIs stay unchanged. Bytes remain temporary (not permanent S3/DB).
Redis is the shared source of truth across API workers when available.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType

logger = logging.getLogger(__name__)

_REDIS_SESSION_PREFIX = "payroll:guest:session:"
_REDIS_SUPPORT_PREFIX = "payroll:guest:support:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_bytes(payload: str) -> bytes:
    return base64.b64decode(payload.encode("ascii"))


@dataclass
class GuestEphemeralSupportingDoc:
    """Temporary supporting document (ID / contract) for guest validation scope."""

    document_id: UUID
    document_type: DocumentType
    content: bytes
    original_filename: str
    mime_type: str
    owner_guest_id: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "document_type": self.document_type.value,
            "content_b64": _encode_bytes(self.content),
            "original_filename": self.original_filename,
            "mime_type": self.mime_type,
            "owner_guest_id": self.owner_guest_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GuestEphemeralSupportingDoc:
        owner = payload.get("owner_guest_id")
        return cls(
            document_id=UUID(str(payload["document_id"])),
            document_type=DocumentType(str(payload["document_type"])),
            content=_decode_bytes(str(payload["content_b64"])),
            original_filename=str(payload.get("original_filename") or "supporting"),
            mime_type=str(payload.get("mime_type") or "application/octet-stream"),
            owner_guest_id=str(owner).strip() if owner else None,
            created_at=datetime.fromisoformat(str(payload["created_at"]))
            if payload.get("created_at")
            else _utcnow(),
            expires_at=datetime.fromisoformat(str(payload["expires_at"]))
            if payload.get("expires_at")
            else None,
        )


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
    owner_guest_id: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "extraction_id": str(self.extraction_id),
            "content_b64": _encode_bytes(self.content),
            "original_filename": self.original_filename,
            "mime_type": self.mime_type,
            "language": self.language,
            "ocr_status": self.ocr_status,
            "parser_status": self.parser_status,
            "ocr_engine": self.ocr_engine,
            "parser_model": self.parser_model,
            "raw_text": self.raw_text,
            "structured_data": self.structured_data,
            "ocr_result": self.ocr_result,
            "warnings": list(self.warnings),
            "error_message": self.error_message,
            "field_confidences": self.field_confidences,
            "dynamic_entries": list(self.dynamic_entries),
            "confirmation_status": self.confirmation_status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "supporting_document_ids": [str(value) for value in self.supporting_document_ids],
            "owner_guest_id": self.owner_guest_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GuestEphemeralSession:
        owner = payload.get("owner_guest_id")
        return cls(
            document_id=UUID(str(payload["document_id"])),
            extraction_id=UUID(str(payload["extraction_id"])),
            content=_decode_bytes(str(payload["content_b64"])),
            original_filename=str(payload.get("original_filename") or "payslip"),
            mime_type=str(payload.get("mime_type") or "application/octet-stream"),
            language=str(payload.get("language") or "auto"),
            ocr_status=str(payload.get("ocr_status") or "pending"),
            parser_status=str(payload.get("parser_status") or "pending"),
            ocr_engine=payload.get("ocr_engine"),
            parser_model=payload.get("parser_model"),
            raw_text=str(payload.get("raw_text") or ""),
            structured_data=dict(payload.get("structured_data") or {}),
            ocr_result=dict(payload.get("ocr_result") or {}),
            warnings=list(payload.get("warnings") or []),
            error_message=payload.get("error_message"),
            field_confidences={
                str(key): float(value)
                for key, value in dict(payload.get("field_confidences") or {}).items()
            },
            dynamic_entries=list(payload.get("dynamic_entries") or []),
            confirmation_status=str(payload.get("confirmation_status") or "review_required"),
            confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"]))
            if payload.get("confirmed_at")
            else None,
            supporting_document_ids=[
                UUID(str(value)) for value in payload.get("supporting_document_ids") or []
            ],
            owner_guest_id=str(owner).strip() if owner else None,
            created_at=datetime.fromisoformat(str(payload["created_at"]))
            if payload.get("created_at")
            else _utcnow(),
            expires_at=datetime.fromisoformat(str(payload["expires_at"]))
            if payload.get("expires_at")
            else None,
        )


def guest_owns_ephemeral(
    record: GuestEphemeralSession | GuestEphemeralSupportingDoc,
    guest_id: str,
) -> bool:
    """Fail closed: missing owner or mismatch means inaccessible."""
    owner = (record.owner_guest_id or "").strip()
    return bool(owner) and owner == guest_id.strip()


class GuestEphemeralStoreProtocol(Protocol):
    def save(self, session: GuestEphemeralSession) -> GuestEphemeralSession: ...

    def get(self, document_id: UUID) -> GuestEphemeralSession | None: ...

    def delete(self, document_id: UUID) -> None: ...

    def update_structured(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None: ...

    def update_dynamic_entries(
        self,
        document_id: UUID,
        *,
        dynamic_entries: list[dict[str, Any]],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None: ...

    def confirm(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any] | None = None,
        dynamic_entries: list[dict[str, Any]] | None = None,
    ) -> GuestEphemeralSession | None: ...

    def save_supporting(
        self,
        *,
        document_type: DocumentType,
        content: bytes,
        original_filename: str,
        mime_type: str,
        payslip_document_id: UUID | None = None,
        owner_guest_id: str | None = None,
    ) -> GuestEphemeralSupportingDoc: ...

    def get_supporting(self, document_id: UUID) -> GuestEphemeralSupportingDoc | None: ...

    def build_document(self, session: GuestEphemeralSession) -> Document: ...

    def build_supporting_document(self, doc: GuestEphemeralSupportingDoc) -> Document: ...

    def build_extraction(self, session: GuestEphemeralSession) -> DocumentExtraction: ...

    def new_ids(self) -> tuple[UUID, UUID]: ...


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
        owner_guest_id: str | None = None,
    ) -> GuestEphemeralSupportingDoc:
        with self._lock:
            self._purge_expired()
            doc = GuestEphemeralSupportingDoc(
                document_id=uuid4(),
                document_type=document_type,
                content=content,
                original_filename=original_filename,
                mime_type=mime_type,
                owner_guest_id=(owner_guest_id or "").strip() or None,
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


class RedisGuestEphemeralStore:
    """Redis-backed guest store shared across API workers."""

    def __init__(self, redis_client: Any, *, ttl_hours: float = 1.0) -> None:
        self._redis = redis_client
        self._ttl = timedelta(hours=ttl_hours)
        self._ttl_seconds = max(60, int(ttl_hours * 3600))
        self._helpers = GuestEphemeralStore(ttl_hours=ttl_hours)

    def _session_key(self, document_id: UUID) -> str:
        return f"{_REDIS_SESSION_PREFIX}{document_id}"

    def _support_key(self, document_id: UUID) -> str:
        return f"{_REDIS_SUPPORT_PREFIX}{document_id}"

    def _save_session(self, session: GuestEphemeralSession) -> GuestEphemeralSession:
        if session.expires_at is None:
            session.expires_at = _utcnow() + self._ttl
        self._redis.set(
            self._session_key(session.document_id),
            json.dumps(session.to_dict()),
            ex=self._ttl_seconds,
        )
        return session

    def _save_support(self, doc: GuestEphemeralSupportingDoc) -> GuestEphemeralSupportingDoc:
        if doc.expires_at is None:
            doc.expires_at = _utcnow() + self._ttl
        self._redis.set(
            self._support_key(doc.document_id),
            json.dumps(doc.to_dict()),
            ex=self._ttl_seconds,
        )
        return doc

    def save(self, session: GuestEphemeralSession) -> GuestEphemeralSession:
        return self._save_session(session)

    def get(self, document_id: UUID) -> GuestEphemeralSession | None:
        raw = self._redis.get(self._session_key(document_id))
        if not raw:
            return None
        session = GuestEphemeralSession.from_dict(json.loads(raw))
        if session.is_expired():
            self.delete(document_id)
            return None
        return session

    def delete(self, document_id: UUID) -> None:
        raw = self._redis.get(self._session_key(document_id))
        supporting_ids: list[UUID] = []
        if raw:
            try:
                session = GuestEphemeralSession.from_dict(json.loads(raw))
                supporting_ids = list(session.supporting_document_ids)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                supporting_ids = []
        self._redis.delete(self._session_key(document_id))
        for sid in supporting_ids:
            self._redis.delete(self._support_key(sid))

    def update_structured(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None:
        session = self.get(document_id)
        if session is None:
            return None
        session.structured_data = structured_data
        if extraction_id is not None:
            session.extraction_id = extraction_id
        if warnings is not None:
            session.warnings = list(dict.fromkeys([*session.warnings, *warnings]))
        return self._save_session(session)

    def update_dynamic_entries(
        self,
        document_id: UUID,
        *,
        dynamic_entries: list[dict[str, Any]],
        warnings: list[str] | None = None,
        extraction_id: UUID | None = None,
    ) -> GuestEphemeralSession | None:
        session = self.get(document_id)
        if session is None:
            return None
        session.dynamic_entries = list(dynamic_entries)
        if extraction_id is not None:
            session.extraction_id = extraction_id
        if warnings is not None:
            session.warnings = list(dict.fromkeys([*session.warnings, *warnings]))
        return self._save_session(session)

    def confirm(
        self,
        document_id: UUID,
        *,
        structured_data: dict[str, Any] | None = None,
        dynamic_entries: list[dict[str, Any]] | None = None,
    ) -> GuestEphemeralSession | None:
        session = self.get(document_id)
        if session is None:
            return None
        if dynamic_entries is not None:
            session.dynamic_entries = list(dynamic_entries)
        if structured_data is not None:
            session.structured_data = deepcopy(structured_data)
        session.confirmation_status = "confirmed"
        session.confirmed_at = _utcnow()
        return self._save_session(session)

    def save_supporting(
        self,
        *,
        document_type: DocumentType,
        content: bytes,
        original_filename: str,
        mime_type: str,
        payslip_document_id: UUID | None = None,
        owner_guest_id: str | None = None,
    ) -> GuestEphemeralSupportingDoc:
        doc = GuestEphemeralSupportingDoc(
            document_id=uuid4(),
            document_type=document_type,
            content=content,
            original_filename=original_filename,
            mime_type=mime_type,
            owner_guest_id=(owner_guest_id or "").strip() or None,
            expires_at=_utcnow() + self._ttl,
        )
        self._save_support(doc)
        if payslip_document_id is not None:
            session = self.get(payslip_document_id)
            if session is not None and doc.document_id not in session.supporting_document_ids:
                session.supporting_document_ids.append(doc.document_id)
                self._save_session(session)
        return doc

    def get_supporting(self, document_id: UUID) -> GuestEphemeralSupportingDoc | None:
        raw = self._redis.get(self._support_key(document_id))
        if not raw:
            return None
        doc = GuestEphemeralSupportingDoc.from_dict(json.loads(raw))
        if doc.is_expired():
            self._redis.delete(self._support_key(document_id))
            return None
        return doc

    def build_document(self, session: GuestEphemeralSession) -> Document:
        return self._helpers.build_document(session)

    def build_supporting_document(self, doc: GuestEphemeralSupportingDoc) -> Document:
        return self._helpers.build_supporting_document(doc)

    def build_extraction(self, session: GuestEphemeralSession) -> DocumentExtraction:
        return self._helpers.build_extraction(session)

    def new_ids(self) -> tuple[UUID, UUID]:
        return uuid4(), uuid4()


_guest_store: GuestEphemeralStoreProtocol | None = None


def get_guest_ephemeral_store(*, ttl_hours: float | None = None) -> GuestEphemeralStoreProtocol:
    global _guest_store
    if _guest_store is not None:
        return _guest_store

    from payroll_copilot.infrastructure.config.production_guards import is_production_env
    from payroll_copilot.infrastructure.config.settings import get_settings

    settings = get_settings()
    resolved_ttl = float(ttl_hours if ttl_hours is not None else settings.guest_ephemeral_ttl_hours)

    try:
        import redis

        from payroll_copilot.infrastructure.config.service_resolver import get_resolved_redis_url

        client = redis.Redis.from_url(
            get_resolved_redis_url(settings),
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        _guest_store = RedisGuestEphemeralStore(client, ttl_hours=resolved_ttl)
        return _guest_store
    except Exception:
        if is_production_env(settings):
            logger.exception("Guest ephemeral store requires Redis in production.")
            raise RuntimeError(
                "Guest ephemeral store requires Redis in production. "
                "Check REDIS_URL connectivity."
            )
        logger.warning(
            "Guest ephemeral store falling back to in-memory (local/dev only).",
            exc_info=False,
        )
        _guest_store = GuestEphemeralStore(ttl_hours=resolved_ttl)
        return _guest_store


def reset_guest_ephemeral_store_for_tests() -> None:
    """Clear the process-local guest store (tests only)."""
    global _guest_store
    _guest_store = None
