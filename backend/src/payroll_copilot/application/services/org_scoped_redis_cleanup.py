"""Organization-scoped Redis cleanup for admin employee data reset.

Never FLUSHALL / FLUSHDB. Only deletes keys discovered via org-scoped indexes
and verified batch job payloads.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_MANUAL_REVIEW_PREFIX = "payroll:manual_review:"
_MANUAL_REVIEW_INDEX_PREFIX = "payroll:manual_review:index:"
_BATCH_PROGRESS_PREFIX = "payroll:batch_progress:"
_BATCH_INDEX_KEY = "payroll:batch_progress:index"
_BATCH_CLAIM_PREFIX = "payroll:batch_claim:"
_GUEST_SESSION_PREFIX = "payroll:guest:session:"
_GUEST_SUPPORT_PREFIX = "payroll:guest:support:"


class RedisClientProtocol(Protocol):
    def get(self, name: str) -> Any: ...

    def delete(self, *names: str) -> Any: ...

    def zrevrange(self, name: str, start: int, end: int) -> Any: ...

    def zrem(self, name: str, *values: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class RedisCleanupCounts:
    manual_review_items: int = 0
    batch_progress_jobs: int = 0
    guest_session_keys: int = 0


def _as_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def clear_manual_review_for_organization(
    redis: RedisClientProtocol,
    organization_id: str,
) -> int:
    org = str(organization_id or "").strip()
    if not org:
        return 0
    index_key = f"{_MANUAL_REVIEW_INDEX_PREFIX}{org}"
    deleted = 0
    ids = redis.zrevrange(index_key, 0, -1) or []
    for raw_id in ids:
        item_id = _as_str(raw_id)
        item_key = f"{_MANUAL_REVIEW_PREFIX}{item_id}"
        raw = redis.get(item_key)
        if raw:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            if str(payload.get("organization_id") or "") == org:
                redis.delete(item_key)
                deleted += 1
        else:
            # Orphan index member — still remove from index below.
            pass
        redis.zrem(index_key, item_id)
    redis.delete(index_key)
    return deleted


def clear_batch_progress_for_organization(
    redis: RedisClientProtocol,
    organization_id: str,
    *,
    scan_limit: int = 500,
) -> int:
    org = str(organization_id or "").strip()
    if not org:
        return 0
    deleted = 0
    ids = redis.zrevrange(_BATCH_INDEX_KEY, 0, max(0, scan_limit - 1)) or []
    for raw_id in ids:
        batch_job_id = _as_str(raw_id)
        progress_key = f"{_BATCH_PROGRESS_PREFIX}{batch_job_id}"
        raw = redis.get(progress_key)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if str(payload.get("organization_id") or "") != org:
            continue
        redis.delete(progress_key)
        redis.delete(f"{_BATCH_CLAIM_PREFIX}{batch_job_id}")
        redis.zrem(_BATCH_INDEX_KEY, batch_job_id)
        deleted += 1
    return deleted


def clear_guest_keys_for_document_ids(
    redis: RedisClientProtocol,
    document_ids: list[str],
) -> int:
    deleted = 0
    for document_id in document_ids:
        doc = str(document_id or "").strip()
        if not doc:
            continue
        for prefix in (_GUEST_SESSION_PREFIX, _GUEST_SUPPORT_PREFIX):
            key = f"{prefix}{doc}"
            if redis.get(key) is not None:
                redis.delete(key)
                deleted += 1
    return deleted


def clear_organization_redis(
    redis: RedisClientProtocol | None,
    organization_id: str,
    *,
    guest_document_ids: list[str] | None = None,
) -> RedisCleanupCounts:
    if redis is None:
        return RedisCleanupCounts()
    try:
        manual = clear_manual_review_for_organization(redis, organization_id)
        batch = clear_batch_progress_for_organization(redis, organization_id)
        guest = clear_guest_keys_for_document_ids(redis, guest_document_ids or [])
        return RedisCleanupCounts(
            manual_review_items=manual,
            batch_progress_jobs=batch,
            guest_session_keys=guest,
        )
    except Exception:
        logger.warning(
            "Organization-scoped Redis cleanup failed for org=%s",
            organization_id,
            exc_info=True,
        )
        return RedisCleanupCounts()
