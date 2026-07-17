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
        service_name="S3",
        configured_url="http://minio:9000",
        local_url="http://localhost:9000",
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=_reachable("http://localhost:9000"),
    )
    assert resolved == "http://localhost:9000"


def test_empty_s3_endpoint_means_amazon_s3() -> None:
    from types import SimpleNamespace

    from payroll_copilot.infrastructure.config.service_resolver import get_resolved_s3_endpoint

    settings = SimpleNamespace(
        s3_endpoint="",
        s3_local_endpoint="http://localhost:9000",
        s3_region="eu-west-1",
        service_auto_fallback=True,
        service_probe_timeout_seconds=0.1,
    )
    assert get_resolved_s3_endpoint(settings) == ""


def test_create_object_storage_uses_custom_endpoint_for_minio(monkeypatch) -> None:
    from types import SimpleNamespace

    from payroll_copilot.infrastructure.storage import factory as storage_factory

    captured: dict = {}

    class _FakeStorage:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(storage_factory, "S3ObjectStorage", _FakeStorage)
    monkeypatch.setattr(
        storage_factory,
        "get_resolved_s3_endpoint",
        lambda settings: "http://localhost:9000",
    )

    settings = SimpleNamespace(
        s3_bucket="payroll-copilot",
        s3_region="us-east-1",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
        s3_use_ssl=False,
        s3_auto_create_bucket=True,
    )
    storage_factory.create_object_storage(settings)
    assert captured["endpoint"] == "http://localhost:9000"
    assert captured["auto_create_bucket"] is True
    assert captured["use_ssl"] is False


def test_create_object_storage_amazon_s3_disables_auto_create(monkeypatch) -> None:
    from types import SimpleNamespace

    from payroll_copilot.infrastructure.storage import factory as storage_factory

    captured: dict = {}

    class _FakeStorage:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(storage_factory, "S3ObjectStorage", _FakeStorage)
    monkeypatch.setattr(storage_factory, "get_resolved_s3_endpoint", lambda settings: "")

    settings = SimpleNamespace(
        s3_bucket="payroll-copilot-prod",
        s3_region="eu-central-1",
        s3_access_key="",
        s3_secret_key="",
        s3_use_ssl=False,
        s3_auto_create_bucket=True,
    )
    storage_factory.create_object_storage(settings)
    assert captured["endpoint"] is None
    assert captured["auto_create_bucket"] is False
    assert captured["use_ssl"] is True
    assert captured["access_key"] is None
    assert captured["secret_key"] is None
