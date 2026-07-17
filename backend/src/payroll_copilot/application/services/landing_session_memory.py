"""Ephemeral landing-session memory — process-local, never persisted to disk/DB."""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class LandingChatTurn:
    role: str
    content: str
    created_at: datetime = field(default_factory=_utcnow)
    kind: str = "text"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class LandingSessionMemory:
    session_id: str
    locale: str = "en"
    turns: list[LandingChatTurn] = field(default_factory=list)
    uploaded_filenames: list[str] = field(default_factory=list)
    uploaded_hashes: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    payslip_document_id: str | None = None
    extracted_fields: list[dict[str, Any]] = field(default_factory=list)
    confirmed_fields: list[dict[str, Any]] = field(default_factory=list)
    validation_run_id: str | None = None
    validation_report: dict[str, Any] | None = None
    field_statuses: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at


class LandingSessionMemoryStore:
    """In-memory chat + document memory for the public landing workflow."""

    def __init__(self, *, ttl_hours: float = 2.0) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._sessions: dict[str, LandingSessionMemory] = {}
        self._lock = threading.RLock()

    def _purge(self) -> None:
        expired = [key for key, session in self._sessions.items() if session.is_expired()]
        for key in expired:
            self._sessions.pop(key, None)

    def get_or_create(self, session_id: str | None, *, locale: str = "en") -> LandingSessionMemory:
        with self._lock:
            self._purge()
            sid = session_id or str(uuid4())
            session = self._sessions.get(sid)
            if session is None or session.is_expired():
                session = LandingSessionMemory(
                    session_id=sid,
                    locale=locale,
                    expires_at=_utcnow() + self._ttl,
                )
                self._sessions[sid] = session
            else:
                session.locale = locale or session.locale
                session.expires_at = _utcnow() + self._ttl
            return session

    def get(self, session_id: str) -> LandingSessionMemory | None:
        with self._lock:
            self._purge()
            session = self._sessions.get(session_id)
            if session is None or session.is_expired():
                self._sessions.pop(session_id, None)
                return None
            return session

    def save(self, session: LandingSessionMemory) -> LandingSessionMemory:
        with self._lock:
            self._purge()
            session.expires_at = _utcnow() + self._ttl
            self._sessions[session.session_id] = session
            return session

    def snapshot(self, session_id: str) -> dict[str, Any] | None:
        session = self.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "locale": session.locale,
            "turns": [
                {
                    "role": turn.role,
                    "content": turn.content,
                    "kind": turn.kind,
                    "meta": deepcopy(turn.meta),
                    "created_at": turn.created_at.isoformat(),
                }
                for turn in session.turns
            ],
            "uploaded_filenames": list(session.uploaded_filenames),
            "document_ids": list(session.document_ids),
            "payslip_document_id": session.payslip_document_id,
            "extracted_fields": deepcopy(session.extracted_fields),
            "confirmed_fields": deepcopy(session.confirmed_fields),
            "validation_run_id": session.validation_run_id,
            "validation_report": deepcopy(session.validation_report),
            "field_statuses": deepcopy(session.field_statuses),
        }

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


_landing_memory_store: LandingSessionMemoryStore | None = None
_landing_memory_lock = threading.Lock()


def get_landing_session_memory_store() -> LandingSessionMemoryStore:
    global _landing_memory_store
    with _landing_memory_lock:
        if _landing_memory_store is None:
            _landing_memory_store = LandingSessionMemoryStore()
        return _landing_memory_store
