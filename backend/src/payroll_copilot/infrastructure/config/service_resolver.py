"""Resolve backend service URLs for local-vs-Docker execution.

Docker Compose networks expose services by hostname (``redis``, ``minio``,
``postgres``). Those names do not resolve when the backend runs directly on a
developer machine. This resolver mirrors the Ollama resolver pattern: it uses the
configured URL when its host is reachable, and otherwise falls back to a
``*_LOCAL_URL`` (localhost) so local execution works without editing shared config.

Only connection reachability is probed — unrelated errors are never swallowed.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

ProbeFn = Callable[[str, float], bool]

_DEFAULT_PORTS = {"redis": 6379, "rediss": 6380, "http": 80, "https": 443}


def _probe_tcp(url: str, timeout_seconds: float) -> bool:
    """Return True if a TCP connection to the URL's host:port succeeds."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or _DEFAULT_PORTS.get(parsed.scheme)
    if port is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def resolve_service_url(
    *,
    service_name: str,
    configured_url: str,
    local_url: str,
    auto_fallback: bool,
    probe_timeout_seconds: float,
    probe: ProbeFn | None = None,
) -> str:
    """Resolve a service URL, preferring the configured URL, falling back to local.

    * Auto-fallback disabled → the configured URL is used as-is.
    * Configured host reachable → use it (Docker keeps using ``redis``/``minio``).
    * Configured unreachable but local reachable → use the local URL (local dev).
    * Neither reachable → keep the configured URL so the eventual failure is clean
      and logged, rather than silently masked.
    """
    if not auto_fallback:
        logger.info("%s URL: auto-fallback disabled, using %s", service_name, configured_url)
        return configured_url

    probe_fn = probe or _probe_tcp

    if probe_fn(configured_url, probe_timeout_seconds):
        logger.info("%s URL: configured host reachable, using %s", service_name, configured_url)
        return configured_url

    logger.info(
        "%s URL: configured host unreachable at %s, trying local fallback",
        service_name,
        configured_url,
    )

    if local_url and local_url != configured_url and probe_fn(local_url, probe_timeout_seconds):
        logger.warning("%s URL: using local fallback %s", service_name, local_url)
        return local_url

    logger.warning(
        "%s URL: no reachable instance; keeping configured %s "
        "(start the service or set the correct URL in .env)",
        service_name,
        configured_url,
    )
    return configured_url


def get_resolved_celery_broker_url(settings: Settings) -> str:
    return resolve_service_url(
        service_name="Celery broker",
        configured_url=settings.celery_broker_url,
        local_url=settings.celery_broker_local_url,
        auto_fallback=settings.service_auto_fallback,
        probe_timeout_seconds=settings.service_probe_timeout_seconds,
    )


def get_resolved_celery_result_backend(settings: Settings) -> str:
    return resolve_service_url(
        service_name="Celery result backend",
        configured_url=settings.celery_result_backend,
        local_url=settings.celery_result_backend_local_url,
        auto_fallback=settings.service_auto_fallback,
        probe_timeout_seconds=settings.service_probe_timeout_seconds,
    )


def get_resolved_redis_url(settings: Settings) -> str:
    return resolve_service_url(
        service_name="Redis",
        configured_url=settings.redis_url,
        local_url=settings.redis_local_url,
        auto_fallback=settings.service_auto_fallback,
        probe_timeout_seconds=settings.service_probe_timeout_seconds,
    )


def get_resolved_s3_endpoint(settings: Settings) -> str:
    """Return a custom S3 endpoint, or empty string for Amazon S3.

    Empty ``s3_endpoint`` means use the default AWS S3 endpoint for ``s3_region``
    (no ``endpoint_url`` passed to boto3). Non-empty values keep the MinIO /
    local-vs-Docker fallback behavior.
    """
    configured = (settings.s3_endpoint or "").strip()
    if not configured:
        logger.info("S3 endpoint: using Amazon S3 (region=%s)", settings.s3_region)
        return ""

    return resolve_service_url(
        service_name="S3",
        configured_url=configured,
        local_url=settings.s3_local_endpoint,
        auto_fallback=settings.service_auto_fallback,
        probe_timeout_seconds=settings.service_probe_timeout_seconds,
    )
