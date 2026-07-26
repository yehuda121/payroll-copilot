"""Manual review queue for low-confidence employee identification.

Never auto-create employees when identification confidence is too low.
Items wait here until a payroll accountant resolves them.

Redis-backed so Celery identify stages and the API share the same queue.
All list/resolve operations are organization-scoped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

LOW_CONFIDENCE_THRESHOLD = 0.75

_REDIS_KEY_PREFIX = "payroll:manual_review:"
_REDIS_INDEX_PREFIX = "payroll:manual_review:index:"


def _index_key(organization_id: str) -> str:
    return f"{_REDIS_INDEX_PREFIX}{organization_id}"


@dataclass
class ManualReviewItem:
    id: str
    organization_id: str
    reason: str
    status: str = "pending"  # pending | resolved_create | resolved_attach | dismissed
    batch_job_id: str | None = None
    national_id_masked: str | None = None
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    resolution_notes: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "reason": self.reason,
            "status": self.status,
            "batch_job_id": self.batch_job_id,
            "national_id_masked": self.national_id_masked,
            "extracted_fields": self.extracted_fields,
            "confidence": self.confidence,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ManualReviewItem:
        return cls(
            id=str(payload["id"]),
            organization_id=str(payload.get("organization_id") or ""),
            reason=str(payload["reason"]),
            status=str(payload.get("status", "pending")),
            batch_job_id=payload.get("batch_job_id"),
            national_id_masked=payload.get("national_id_masked"),
            extracted_fields=dict(payload.get("extracted_fields") or {}),
            confidence=payload.get("confidence"),
            resolution_notes=payload.get("resolution_notes"),
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
            resolved_at=payload.get("resolved_at"),
        )


class ManualReviewQueueProtocol(Protocol):
    def enqueue(
        self,
        *,
        organization_id: str,
        reason: str,
        confidence: float | None = None,
        batch_job_id: str | None = None,
        national_id_masked: str | None = None,
        extracted_fields: dict[str, Any] | None = None,
    ) -> ManualReviewItem: ...

    def list_pending(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]: ...

    def list_all(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]: ...

    def resolve(
        self,
        item_id: str,
        *,
        organization_id: str,
        status: str,
        notes: str | None = None,
    ) -> ManualReviewItem | None: ...


class InMemoryManualReviewQueue:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: dict[str, ManualReviewItem] = {}

    def enqueue(
        self,
        *,
        organization_id: str,
        reason: str,
        confidence: float | None = None,
        batch_job_id: str | None = None,
        national_id_masked: str | None = None,
        extracted_fields: dict[str, Any] | None = None,
    ) -> ManualReviewItem:
        org = str(organization_id or "").strip()
        if not org:
            raise ValueError("organization_id_required")
        item = ManualReviewItem(
            id=str(uuid4()),
            organization_id=org,
            reason=reason,
            confidence=confidence,
            batch_job_id=batch_job_id,
            national_id_masked=national_id_masked,
            extracted_fields=extracted_fields or {},
        )
        with self._lock:
            self._items[item.id] = item
        return item

    def list_pending(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]:
        with self._lock:
            pending = [
                item
                for item in self._items.values()
                if item.status == "pending" and item.organization_id == organization_id
            ]
            pending.sort(key=lambda item: item.created_at, reverse=True)
            return pending[:limit]

    def list_all(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]:
        with self._lock:
            items = [
                item
                for item in self._items.values()
                if item.organization_id == organization_id
            ]
            items.sort(key=lambda item: item.created_at, reverse=True)
            return items[:limit]

    def resolve(
        self,
        item_id: str,
        *,
        organization_id: str,
        status: str,
        notes: str | None = None,
    ) -> ManualReviewItem | None:
        with self._lock:
            item = self._items.get(item_id)
            if item is None or item.organization_id != organization_id:
                return None
            item.status = status
            item.resolution_notes = notes
            item.resolved_at = datetime.now(UTC).isoformat()
            return item


ManualReviewQueue = InMemoryManualReviewQueue


class RedisManualReviewQueue:
    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def enqueue(
        self,
        *,
        organization_id: str,
        reason: str,
        confidence: float | None = None,
        batch_job_id: str | None = None,
        national_id_masked: str | None = None,
        extracted_fields: dict[str, Any] | None = None,
    ) -> ManualReviewItem:
        org = str(organization_id or "").strip()
        if not org:
            raise ValueError("organization_id_required")
        item = ManualReviewItem(
            id=str(uuid4()),
            organization_id=org,
            reason=reason,
            confidence=confidence,
            batch_job_id=batch_job_id,
            national_id_masked=national_id_masked,
            extracted_fields=extracted_fields or {},
        )
        self._save(item)
        self._redis.zadd(_index_key(org), {item.id: datetime.now(UTC).timestamp()})
        return item

    def list_pending(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]:
        return [
            item
            for item in self.list_all(organization_id, limit=limit)
            if item.status == "pending"
        ]

    def list_all(
        self, organization_id: str, *, limit: int = 100
    ) -> list[ManualReviewItem]:
        org = str(organization_id or "").strip()
        if not org:
            return []
        ids = self._redis.zrevrange(_index_key(org), 0, max(0, limit - 1))
        items: list[ManualReviewItem] = []
        for raw_id in ids:
            item_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            raw = self._redis.get(f"{_REDIS_KEY_PREFIX}{item_id}")
            if not raw:
                continue
            item = ManualReviewItem.from_dict(json.loads(raw))
            # Fail closed: skip items that drifted or lack org ownership.
            if item.organization_id != org:
                continue
            items.append(item)
        return items

    def resolve(
        self,
        item_id: str,
        *,
        organization_id: str,
        status: str,
        notes: str | None = None,
    ) -> ManualReviewItem | None:
        org = str(organization_id or "").strip()
        raw = self._redis.get(f"{_REDIS_KEY_PREFIX}{item_id}")
        if not raw:
            return None
        item = ManualReviewItem.from_dict(json.loads(raw))
        if not org or item.organization_id != org:
            return None
        item.status = status
        item.resolution_notes = notes
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save(item)
        return item

    def _save(self, item: ManualReviewItem) -> None:
        self._redis.set(f"{_REDIS_KEY_PREFIX}{item.id}", json.dumps(item.to_dict()))


_QUEUE: ManualReviewQueueProtocol | None = None


def get_manual_review_queue() -> ManualReviewQueueProtocol:
    global _QUEUE
    if _QUEUE is not None:
        return _QUEUE
    try:
        import redis

        from payroll_copilot.infrastructure.config.service_resolver import get_resolved_redis_url
        from payroll_copilot.infrastructure.config.settings import get_settings

        client = redis.Redis.from_url(get_resolved_redis_url(get_settings()), decode_responses=True)
        client.ping()
        _QUEUE = RedisManualReviewQueue(client)
    except Exception:  # noqa: BLE001
        _QUEUE = InMemoryManualReviewQueue()
    return _QUEUE


def should_enqueue_low_confidence(confidence: float | None) -> bool:
    if confidence is None:
        return True
    return confidence < LOW_CONFIDENCE_THRESHOLD
