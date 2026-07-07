"""Resolve Ollama base URL: explicit env → local host → Docker host → Docker service.

Resolution is probe-based so the same code works whether the backend runs directly
on the host (local dev) or inside Docker:

* Local execution reaches Ollama on ``127.0.0.1`` / ``localhost``.
* Inside a container, ``127.0.0.1`` is the container itself (no Ollama), so the probe
  moves on to ``host.docker.internal`` (host gateway) and finally the optional
  ``ollama`` Docker service.

No Ollama instance is ever downloaded or started here; unreachable candidates are
simply skipped.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx

if TYPE_CHECKING:
    from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

ProbeFn = Callable[[str, float], bool]


def _probe_ollama(base_url: str, timeout_seconds: float) -> bool:
    """Return True if an Ollama instance responds at base_url."""
    tags_url = urljoin(base_url.rstrip("/") + "/", "api/tags")
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(tags_url)
            return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def resolve_ollama_base_url(
    *,
    explicit_url: str,
    local_url: str,
    host_url: str,
    docker_url: str,
    auto_fallback: bool,
    probe_timeout_seconds: float,
    probe: ProbeFn | None = None,
) -> str:
    """Resolve the Ollama API base URL.

    Priority:
      1. ``OLLAMA_BASE_URL`` when set (non-empty) — used as-is, no probing.
      2. Auto-fallback (default): probe candidates in order and use the first that
         responds — local host, then Docker host gateway, then Docker service.
      3. Auto-fallback disabled: use the local URL deterministically.

    When auto-fallback is enabled but nothing responds, the local URL is returned so
    that the eventual failure is a clean connection error against a real address
    (surfaced as a controlled response by the caller) rather than a DNS failure.
    """
    if explicit_url.strip():
        resolved = explicit_url.rstrip("/")
        logger.info("Ollama URL: using explicit OLLAMA_BASE_URL=%s", resolved)
        return resolved

    if not auto_fallback:
        resolved = (local_url or docker_url).rstrip("/")
        logger.info("Ollama URL: auto-fallback disabled, using %s", resolved)
        return resolved

    probe_fn = probe or _probe_ollama
    candidates = (
        ("local host Ollama", local_url),
        ("Docker host gateway", host_url),
        ("Docker Ollama service", docker_url),
    )

    for label, url in candidates:
        cleaned = url.strip().rstrip("/")
        if not cleaned:
            continue
        if probe_fn(cleaned, probe_timeout_seconds):
            logger.info("Ollama URL: %s reachable at %s", label, cleaned)
            return cleaned
        logger.info("Ollama URL: %s not reachable at %s", label, cleaned)

    fallback = local_url.rstrip("/")
    logger.warning(
        "Ollama URL: no reachable instance found; defaulting to %s. "
        "Start host Ollama ('ollama serve') or the optional docker-ollama profile.",
        fallback,
    )
    return fallback


def get_resolved_ollama_base_url(settings: Settings) -> str:
    """Resolve Ollama URL from application settings."""
    return resolve_ollama_base_url(
        explicit_url=settings.ollama_base_url,
        local_url=settings.ollama_local_url,
        host_url=settings.ollama_host_url,
        docker_url=settings.ollama_docker_url,
        auto_fallback=settings.ollama_auto_fallback,
        probe_timeout_seconds=settings.ollama_probe_timeout_seconds,
    )
