"""Central capability-based model-provider routing.

This is the only runtime module that maps provider names and capabilities to
concrete adapters and model configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from payroll_copilot.application.ports import AICapability, ModelProvider

ProviderBuilder = Callable[[Any, str], ModelProvider]


@dataclass(frozen=True, slots=True)
class AIProviderRoute:
    capability: AICapability
    provider_name: str
    model: str
    provider: ModelProvider


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    builder: ProviderBuilder
    model_setting: str
    default_model: str


def _build_ollama(settings: Any, model: str) -> ModelProvider:
    from payroll_copilot.infrastructure.ai.ollama_provider import OllamaProvider
    from payroll_copilot.infrastructure.config.ollama_resolver import (
        get_resolved_ollama_base_url,
    )

    return OllamaProvider(
        base_url=get_resolved_ollama_base_url(settings),
        default_model=model,
        embedding_model=settings.ollama_embedding_model,
    )


def _build_openai(settings: Any, model: str) -> ModelProvider:
    from payroll_copilot.infrastructure.ai.openai_provider import OpenAIProvider

    return OpenAIProvider(
        api_key=getattr(settings, "openai_api_key", ""),
        model=model,
        embedding_model=getattr(
            settings,
            "openai_embedding_model",
            "text-embedding-3-small",
        ),
        embedding_dimensions=int(
            getattr(settings, "openai_embedding_dimensions", 1536) or 1536
        ),
        timeout_seconds=float(
            getattr(settings, "openai_timeout_seconds", 120.0) or 120.0
        ),
        max_retries=int(getattr(settings, "openai_max_retries", 2) or 0),
        reasoning_effort=getattr(
            settings,
            "openai_reasoning_effort",
            "minimal",
        ),
        base_url=getattr(settings, "openai_base_url", "") or None,
    )


def _build_bedrock(settings: Any, model: str) -> ModelProvider:
    from payroll_copilot.infrastructure.ai.bedrock_provider import BedrockProvider

    return BedrockProvider(
        region=getattr(settings, "bedrock_region", None) or "us-east-1",
        model_id=model,
        embedding_model_id=getattr(settings, "bedrock_embedding_model_id", "")
        or "amazon.titan-embed-text-v2:0",
        embedding_dimensions=int(
            getattr(settings, "bedrock_embedding_dimensions", 1024) or 1024
        ),
        endpoint_url=(getattr(settings, "bedrock_endpoint", None) or "").strip()
        or None,
    )


DEFAULT_PROVIDER_REGISTRY: Mapping[str, ProviderRegistration] = {
    "ollama": ProviderRegistration(
        builder=_build_ollama,
        model_setting="ollama_default_model",
        default_model="llama3.1:8b",
    ),
    "openai": ProviderRegistration(
        builder=_build_openai,
        model_setting="openai_model",
        default_model="gpt-5",
    ),
    "bedrock": ProviderRegistration(
        builder=_build_bedrock,
        model_setting="bedrock_model_id",
        default_model="",
    ),
}


class AIProviderRouter:
    """Resolve one concrete provider per AI capability from configuration."""

    def __init__(
        self,
        settings: Any,
        *,
        provider_registry: Mapping[str, ProviderRegistration] | None = None,
    ) -> None:
        self._settings = settings
        self._registry = dict(provider_registry or DEFAULT_PROVIDER_REGISTRY)
        self._provider_cache: dict[tuple[str, str], ModelProvider] = {}

    def route(self, capability: AICapability) -> AIProviderRoute:
        provider_name = self.provider_name_for(capability)
        model = self.model_for(capability, provider_name=provider_name)
        key = (provider_name, model)
        provider = self._provider_cache.get(key)
        if provider is None:
            registration = self._registry.get(provider_name)
            if registration is None:
                supported = ", ".join(sorted(self._registry))
                raise ValueError(
                    f"Unsupported model provider: {provider_name}. "
                    f"Supported providers: {supported}."
                )
            provider = registration.builder(self._settings, model)
            self._provider_cache[key] = provider
        return AIProviderRoute(
            capability=capability,
            provider_name=provider_name,
            model=model,
            provider=provider,
        )

    def provider_for(self, capability: AICapability) -> ModelProvider:
        return self.route(capability).provider

    def provider_name_for(self, capability: AICapability) -> str:
        capability_value = str(
            getattr(self._settings, f"{capability.value}_provider", "") or ""
        ).strip()
        legacy_value = str(
            getattr(self._settings, "model_provider", "") or "bedrock"
        ).strip()
        return (capability_value or legacy_value or "bedrock").lower()

    def model_for(
        self,
        capability: AICapability,
        *,
        provider_name: str | None = None,
    ) -> str:
        name = provider_name or self.provider_name_for(capability)
        if capability is AICapability.PAYSLIP_EXTRACTION:
            override = str(
                getattr(self._settings, "payslip_parser_model", "") or ""
            ).strip()
            if override:
                return override
        registration = self._registry.get(name)
        if registration is None:
            return ""
        return str(
            getattr(self._settings, registration.model_setting, "")
            or registration.default_model
        ).strip()


def create_provider_by_name(
    provider_name: str,
    settings: Any,
    *,
    model: str | None = None,
) -> ModelProvider:
    """Compatibility factory for integrations that select an explicit provider."""
    normalized = (provider_name or "bedrock").strip().lower()
    router = AIProviderRouter(settings)
    resolved_model = model or router.model_for(
        AICapability.GENERAL,
        provider_name=normalized,
    )
    registration = DEFAULT_PROVIDER_REGISTRY.get(normalized)
    if registration is None:
        supported = ", ".join(sorted(DEFAULT_PROVIDER_REGISTRY))
        raise ValueError(
            f"Unsupported model provider: {provider_name}. "
            f"Supported providers: {supported}."
        )
    return registration.builder(settings, resolved_model)


@lru_cache
def get_ai_provider_router() -> AIProviderRouter:
    from payroll_copilot.infrastructure.config.settings import get_settings

    return AIProviderRouter(get_settings())
