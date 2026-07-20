"""Fixed-window request rate limiting (Redis-backed with in-memory fallback)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from payroll_copilot.infrastructure.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    scope: str
    identifier: str
    limit: int
    window_seconds: int


class RateLimiter:
    """Enforce per-scope counters. Production uses Redis; dev/tests fall back to memory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis: Any | None | bool = None
        self._memory_lock = threading.Lock()
        self._memory: dict[str, tuple[int, float]] = {}

    @property
    def enforced(self) -> bool:
        return self._settings.rate_limit_enforced

    def enforce(self, scope: str, identifier: str, limit: int, window_seconds: int) -> None:
        if not self.enforced or limit <= 0:
            return
        policy = RateLimitPolicy(
            scope=scope,
            identifier=identifier or "unknown",
            limit=limit,
            window_seconds=window_seconds,
        )
        count = self._increment(policy)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "scope": scope,
                    "retry_after_seconds": window_seconds,
                },
                headers={"Retry-After": str(window_seconds)},
            )

    def _increment(self, policy: RateLimitPolicy) -> int:
        bucket = int(time.time()) // policy.window_seconds
        key = f"rl:{policy.scope}:{policy.identifier}:{policy.window_seconds}:{bucket}"
        client = self._redis_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(key)
                pipe.expire(key, policy.window_seconds)
                count, _ = pipe.execute()
                return int(count)
            except Exception:
                logger.warning("Rate limit Redis unavailable; using in-memory fallback.", exc_info=True)
        return self._memory_increment(key, policy.window_seconds)

    def _memory_increment(self, key: str, window_seconds: int) -> int:
        now = time.time()
        expiry = now + window_seconds
        with self._memory_lock:
            count, expires_at = self._memory.get(key, (0, 0.0))
            if expires_at <= now:
                count = 0
            count += 1
            self._memory[key] = (count, expiry)
            if len(self._memory) > 10_000:
                self._memory = {
                    k: v for k, v in self._memory.items() if v[1] > now
                }
            return count

    def _redis_client(self) -> Any | None:
        if self._redis is False:
            return None
        if self._redis is not None:
            return self._redis
        try:
            import redis

            from payroll_copilot.infrastructure.config.service_resolver import get_resolved_redis_url

            client = redis.Redis.from_url(
                get_resolved_redis_url(self._settings),
                decode_responses=True,
            )
            client.ping()
            self._redis = client
            return client
        except Exception:
            self._redis = False
            return None


_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = RateLimiter()
    return _limiter


def reset_rate_limiter_for_tests() -> None:
    global _limiter
    with _limiter_lock:
        _limiter = None
