"""Unit tests for Ollama base URL resolution."""

from __future__ import annotations

from payroll_copilot.infrastructure.config.ollama_resolver import resolve_ollama_base_url

LOCAL = "http://127.0.0.1:11434"
HOST = "http://host.docker.internal:11434"
DOCKER = "http://ollama:11434"


def _resolve(reachable: set[str]) -> str:
    def probe(url: str, _timeout: float) -> bool:
        return url in reachable

    return resolve_ollama_base_url(
        explicit_url="",
        local_url=LOCAL,
        host_url=HOST,
        docker_url=DOCKER,
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=probe,
    )


def test_local_backend_prefers_localhost_when_available() -> None:
    # Local host Ollama reachable — and even if the others are too, local wins.
    assert _resolve({LOCAL, HOST, DOCKER}) == LOCAL


def test_docker_host_gateway_used_when_local_unavailable() -> None:
    assert _resolve({HOST, DOCKER}) == HOST


def test_docker_service_is_fallback_only() -> None:
    assert _resolve({DOCKER}) == DOCKER


def test_no_reachable_instance_defaults_to_local_without_crashing() -> None:
    # Must not raise; returns a real (local) address so failures are clean ConnectErrors.
    assert _resolve(set()) == LOCAL


def test_explicit_base_url_bypasses_probing() -> None:
    def probe(_url: str, _timeout: float) -> bool:  # pragma: no cover - must not run
        raise AssertionError("probe must not be called when OLLAMA_BASE_URL is set")

    resolved = resolve_ollama_base_url(
        explicit_url="http://explicit-ollama:11434/",
        local_url=LOCAL,
        host_url=HOST,
        docker_url=DOCKER,
        auto_fallback=True,
        probe_timeout_seconds=0.1,
        probe=probe,
    )
    assert resolved == "http://explicit-ollama:11434"


def test_auto_fallback_disabled_uses_local_url() -> None:
    def probe(_url: str, _timeout: float) -> bool:  # pragma: no cover - must not run
        raise AssertionError("probe must not be called when auto-fallback is disabled")

    resolved = resolve_ollama_base_url(
        explicit_url="",
        local_url=LOCAL,
        host_url=HOST,
        docker_url=DOCKER,
        auto_fallback=False,
        probe_timeout_seconds=0.1,
        probe=probe,
    )
    assert resolved == LOCAL
