"""Unit tests for local-vs-Docker service URL resolution."""

from __future__ import annotations

from payroll_copilot.infrastructure.config.service_resolver import resolve_service_url

_DOCKER_URL = "redis://redis:6379/1"
_LOCAL_URL = "redis://localhost:6379/1"


def _reachable(*reachable_urls: str):
    def probe(url: str, timeout: float) -> bool:
        return url in reachable_urls

    return probe


def test_configured_url_used_when_reachable() -> None:
    """In Docker, the `redis` hostname is reachable and must be used."""
    resolved = resolve_service_url(
        service_name="Redis",
        configured_url=_DOCKER_URL,
        local_url=_LOCAL_URL,
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=_reachable(_DOCKER_URL),
    )
    assert resolved == _DOCKER_URL


def test_local_fallback_used_when_configured_unreachable() -> None:
    """Running locally, `redis` fails to resolve and the local URL is used."""
    resolved = resolve_service_url(
        service_name="Redis",
        configured_url=_DOCKER_URL,
        local_url=_LOCAL_URL,
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=_reachable(_LOCAL_URL),
    )
    assert resolved == _LOCAL_URL


def test_configured_url_kept_when_nothing_reachable() -> None:
    """When neither is reachable, keep configured so the failure is clean/logged."""
    resolved = resolve_service_url(
        service_name="Redis",
        configured_url=_DOCKER_URL,
        local_url=_LOCAL_URL,
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=_reachable(),
    )
    assert resolved == _DOCKER_URL


def test_auto_fallback_disabled_returns_configured_without_probing() -> None:
    calls: list[str] = []

    def probe(url: str, timeout: float) -> bool:
        calls.append(url)
        return False

    resolved = resolve_service_url(
        service_name="Redis",
        configured_url=_DOCKER_URL,
        local_url=_LOCAL_URL,
        auto_fallback=False,
        probe_timeout_seconds=0.1,
        probe=probe,
    )
    assert resolved == _DOCKER_URL
    assert calls == []


def test_s3_endpoint_local_fallback() -> None:
    resolved = resolve_service_url(
        service_name="S3/MinIO",
        configured_url="http://minio:9000",
        local_url="http://localhost:9000",
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=_reachable("http://localhost:9000"),
    )
    assert resolved == "http://localhost:9000"
