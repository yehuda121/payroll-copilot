"""Process-local conversation summary for assistant chat follow-ups.

Not used for authentication. Not persisted to disk/DB. Keyed by session_id.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class ConversationSummary:
    session_id: str
    last_period: str | None = None
    last_payslip: str | None = None
    last_document: str | None = None
    last_validation: str | None = None
    current_topic: str | None = None
    last_user_question: str | None = None
    updated_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and _utcnow() >= self.expires_at

    def to_public_dict(self) -> dict[str, Any]:
        """Facts-only payload safe to include in tool context."""
        return {
            "last_period": self.last_period,
            "last_payslip": self.last_payslip,
            "last_document": self.last_document,
            "last_validation": self.last_validation,
            "current_topic": self.current_topic,
            "last_user_question": self.last_user_question,
        }


class ConversationSummaryStore:
    """In-memory rolling summary store (same pattern as landing session memory)."""

    def __init__(self, *, ttl_hours: float = 8.0) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._items: dict[str, ConversationSummary] = {}
        self._lock = threading.RLock()

    def _purge(self) -> None:
        expired = [key for key, item in self._items.items() if item.is_expired()]
        for key in expired:
            self._items.pop(key, None)

    def get(self, session_id: str | None) -> ConversationSummary | None:
        if not session_id:
            return None
        with self._lock:
            self._purge()
            item = self._items.get(session_id)
            if item is None or item.is_expired():
                self._items.pop(session_id, None)
                return None
            return item

    def get_or_create(self, session_id: str) -> ConversationSummary:
        with self._lock:
            self._purge()
            item = self._items.get(session_id)
            if item is None or item.is_expired():
                item = ConversationSummary(
                    session_id=session_id,
                    expires_at=_utcnow() + self._ttl,
                )
                self._items[session_id] = item
            else:
                item.expires_at = _utcnow() + self._ttl
            return item

    def update_from_turn(
        self,
        session_id: str,
        *,
        strategy: str | None,
        period_key: str | None,
        loaded_resource_keys: list[str] | None = None,
        validation_run_id: str | None = None,
        user_question: str | None = None,
        document_hint: str | None = None,
    ) -> ConversationSummary:
        with self._lock:
            item = self.get_or_create(session_id)
            if strategy:
                item.current_topic = strategy
            if period_key:
                item.last_period = period_key
                item.last_payslip = period_key
            keys = loaded_resource_keys or []
            for key in keys:
                if key.startswith("payroll_month_detail:") or key.startswith("review_document:"):
                    period = key.split(":", 1)[-1]
                    if len(period) >= 7 and period[4] == "-":
                        item.last_period = period[:7]
                        item.last_payslip = period[:7]
                if key == "employee_documents":
                    item.last_document = document_hint or item.last_document or "employee_documents"
            if validation_run_id:
                item.last_validation = validation_run_id
            if user_question:
                item.last_user_question = user_question.strip()[:240] or item.last_user_question
            if document_hint:
                item.last_document = document_hint
            item.updated_at = _utcnow()
            item.expires_at = _utcnow() + self._ttl
            return item


_store: ConversationSummaryStore | None = None
_store_lock = threading.Lock()


def get_conversation_summary_store() -> ConversationSummaryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ConversationSummaryStore()
        return _store
