"""Resolve Ollama base URL: explicit env → host → Docker fallback."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)


def _probe_ollama(base_url: str, timeout_seconds: float) -> bool:
    """Return True if Ollama responds at base_url."""
    tags_url = urljoin(base_url.rstrip("/") + "/", "api/tags")
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(tags_url)
            return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@lru_cache(maxsize=1)
def resolve_ollama_base_url(
    explicit_url: str,
    host_url: str,
    docker_url: str,
    auto_fallback: bool,
    probe_timeout_seconds: float,
) -> str:
    """
    Resolve the Ollama API base URL.

    Priority:
    1. OLLAMA_BASE_URL when set (non-empty) — used as-is, no probing
    2. OLLAMA_HOST_URL when auto-fallback enabled and reachable
    3. OLLAMA_DOCKER_URL
    """
    if explicit_url.strip():
        resolved = explicit_url.rstrip("/")
        logger.info("Ollama URL: using explicit OLLAMA_BASE_URL=%s", resolved)
        return resolved

    if auto_fallback:
        host = host_url.rstrip("/")
        if _probe_ollama(host, probe_timeout_seconds):
            logger.info("Ollama URL: host instance reachable at %s", host)
            return host
        logger.info(
            "Ollama URL: host instance unreachable at %s, falling back to Docker service",
            host,
        )

    resolved = docker_url.rstrip("/")
    logger.info("Ollama URL: using OLLAMA_DOCKER_URL=%s", resolved)
    return resolved


def get_resolved_ollama_base_url(settings: Settings) -> str:
    """Resolve Ollama URL from application settings."""
    return resolve_ollama_base_url(
        explicit_url=settings.ollama_base_url,
        host_url=settings.ollama_host_url,
        docker_url=settings.ollama_docker_url,
        auto_fallback=settings.ollama_auto_fallback,
        probe_timeout_seconds=settings.ollama_probe_timeout_seconds,
    )
