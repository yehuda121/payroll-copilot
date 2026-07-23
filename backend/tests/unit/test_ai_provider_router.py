"""Capability routing and OpenAI provider contract tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pydantic import BaseModel

from payroll_copilot.application.ports import AICapability, Message
from payroll_copilot.infrastructure.ai.openai_provider import OpenAIProvider
from payroll_copilot.infrastructure.ai.provider_router import (
    AIProviderRoute,
    AIProviderRouter,
    ProviderRegistration,
)
from payroll_copilot.infrastructure.ai.payslip_parser_factory import (
    create_payslip_parser,
)


class _FakeProvider:
    embedding_dimensions = 3

    async def complete(self, messages, **kwargs):  # pragma: no cover - port stub
        raise NotImplementedError

    async def complete_structured(self, messages, response_schema, **kwargs):
        raise NotImplementedError

    async def embed(self, texts):
        raise NotImplementedError


def _settings(**overrides):
    values = {
        "model_provider": "bedrock",
        "payslip_extraction_provider": "",
        "document_extraction_provider": "",
        "assistant_provider": "",
        "employee_chat_provider": "",
        "accountant_chat_provider": "",
        "rag_provider": "",
        "embeddings_provider": "",
        "general_provider": "",
        "payslip_parser_model": "",
        "ollama_default_model": "local-model",
        "openai_model": "gpt-5",
        "bedrock_model_id": "bedrock-model",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_capabilities_route_independently_and_cache_matching_routes() -> None:
    built: list[tuple[str, str]] = []

    def builder(name: str):
        def build(_settings, model):
            built.append((name, model))
            return _FakeProvider()

        return build

    router = AIProviderRouter(
        _settings(
            payslip_extraction_provider="openai",
            document_extraction_provider="openai",
            assistant_provider="ollama",
            employee_chat_provider="ollama",
            accountant_chat_provider="ollama",
        ),
        provider_registry={
            "openai": ProviderRegistration(
                builder("openai"), "openai_model", "gpt-5"
            ),
            "ollama": ProviderRegistration(
                builder("ollama"), "ollama_default_model", "local-model"
            ),
            "bedrock": ProviderRegistration(
                builder("bedrock"), "bedrock_model_id", ""
            ),
        },
    )

    payslip = router.route(AICapability.PAYSLIP_EXTRACTION)
    document = router.route(AICapability.DOCUMENT_EXTRACTION)
    assistant = router.route(AICapability.ASSISTANT)
    employee = router.route(AICapability.EMPLOYEE_CHAT)
    accountant = router.route(AICapability.ACCOUNTANT_CHAT)

    assert payslip.provider_name == "openai"
    assert document.provider_name == "openai"
    assert assistant.provider_name == "ollama"
    assert employee.provider_name == "ollama"
    assert accountant.provider_name == "ollama"
    assert payslip.provider is document.provider
    assert assistant.provider is employee.provider is accountant.provider
    assert built == [("openai", "gpt-5"), ("ollama", "local-model")]


def test_missing_capability_config_falls_back_to_legacy_model_provider() -> None:
    router = AIProviderRouter(
        _settings(model_provider="ollama"),
        provider_registry={
            "ollama": ProviderRegistration(
                lambda _settings, _model: _FakeProvider(),
                "ollama_default_model",
                "local-model",
            )
        },
    )
    for capability in AICapability:
        assert router.provider_name_for(capability) == "ollama"


def test_current_default_remains_bedrock_when_all_provider_config_is_empty() -> None:
    router = AIProviderRouter(_settings(model_provider=""))
    assert router.provider_name_for(AICapability.GENERAL) == "bedrock"


def test_payslip_model_override_is_centralized() -> None:
    router = AIProviderRouter(
        _settings(
            payslip_extraction_provider="openai",
            payslip_parser_model="gpt-5-mini",
        )
    )
    assert router.model_for(AICapability.PAYSLIP_EXTRACTION) == "gpt-5-mini"
    assert (
        router.model_for(
            AICapability.DOCUMENT_EXTRACTION,
            provider_name="openai",
        )
        == "gpt-5"
    )


def test_payslip_parser_requests_only_the_payslip_capability() -> None:
    provider = _FakeProvider()
    router = Mock()
    router.route.return_value = AIProviderRoute(
        capability=AICapability.PAYSLIP_EXTRACTION,
        provider_name="openai",
        model="gpt-5",
        provider=provider,
    )
    parser = create_payslip_parser(_settings(), router=router)
    router.route.assert_called_once_with(AICapability.PAYSLIP_EXTRACTION)
    assert parser._provider is provider
    assert parser._model == "gpt-5"


def test_chat_capabilities_can_resolve_to_distinct_providers() -> None:
    """Public, employee, and accountant chat must not share one hard-coded route."""
    built: dict[str, _FakeProvider] = {}

    def builder(name: str):
        def build(_settings, model):
            provider = _FakeProvider()
            built[name] = provider
            return provider

        return build

    router = AIProviderRouter(
        _settings(
            assistant_provider="ollama",
            employee_chat_provider="openai",
            accountant_chat_provider="bedrock",
        ),
        provider_registry={
            "openai": ProviderRegistration(
                builder("openai"), "openai_model", "gpt-5"
            ),
            "ollama": ProviderRegistration(
                builder("ollama"), "ollama_default_model", "local-model"
            ),
            "bedrock": ProviderRegistration(
                builder("bedrock"), "bedrock_model_id", "bedrock-model"
            ),
        },
    )
    assistant = router.route(AICapability.ASSISTANT)
    employee = router.route(AICapability.EMPLOYEE_CHAT)
    accountant = router.route(AICapability.ACCOUNTANT_CHAT)
    assert assistant.provider_name == "ollama"
    assert employee.provider_name == "openai"
    assert accountant.provider_name == "bedrock"
    assert assistant.provider.inner is built["ollama"]
    assert employee.provider.inner is built["openai"]
    assert accountant.provider.inner is built["bedrock"]
    assert len({id(assistant.provider), id(employee.provider), id(accountant.provider)}) == 3


class _StructuredPayload(BaseModel):
    amount: int


async def test_openai_provider_complete_structured_and_embed() -> None:
    create_completion = AsyncMock(
        side_effect=[
            SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="hello"))
                ],
                usage=SimpleNamespace(total_tokens=11),
                model="gpt-5",
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"amount": 42}')
                    )
                ],
                usage=SimpleNamespace(total_tokens=17),
                model="gpt-5",
            ),
        ]
    )
    create_embedding = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.4, 0.5, 0.6]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3]),
            ]
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_completion)
        ),
        embeddings=SimpleNamespace(create=create_embedding),
    )
    provider = OpenAIProvider(
        api_key="",
        model="gpt-5",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=3,
        client=client,
    )

    result = await provider.complete(
        [Message(role="user", content="Hi")],
        temperature=0.0,
        max_tokens=100,
    )
    structured = await provider.complete_structured(
        [Message(role="user", content="Return amount")],
        _StructuredPayload,
    )
    embeddings = await provider.embed(["first", "second"])

    assert result.content == "hello"
    assert result.tokens_used == 11
    assert structured.data.amount == 42
    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    first_call = create_completion.await_args_list[0].kwargs
    assert first_call["model"] == "gpt-5"
    assert first_call["max_completion_tokens"] == 100
    assert "temperature" not in first_call
    assert first_call["reasoning_effort"] == "minimal"
    structured_call = create_completion.await_args_list[1].kwargs
    assert structured_call["response_format"] == {"type": "json_object"}
    create_embedding.assert_awaited_once_with(
        model="text-embedding-3-small",
        input=["first", "second"],
        dimensions=3,
    )
