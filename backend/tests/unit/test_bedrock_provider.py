"""Unit tests for model provider factory (Bedrock / Ollama)."""

from __future__ import annotations

from payroll_copilot.infrastructure.ai.bedrock_provider import BedrockProvider
from payroll_copilot.infrastructure.ai.ollama_provider import OllamaProvider, create_model_provider


class _FakeSettings:
    model_provider = "bedrock"
    bedrock_region = "us-east-1"
    bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_embedding_model_id = "amazon.titan-embed-text-v2:0"
    bedrock_embedding_dimensions = 1024
    bedrock_endpoint = ""
    ollama_base_url = "http://127.0.0.1:11434"
    ollama_local_url = "http://127.0.0.1:11434"
    ollama_host_url = "http://host.docker.internal:11434"
    ollama_docker_url = "http://ollama:11434"
    ollama_auto_fallback = False
    ollama_probe_timeout_seconds = 0.1
    ollama_default_model = "llama3.1:8b"
    ollama_embedding_model = "nomic-embed-text"


def test_create_model_provider_bedrock() -> None:
    provider = create_model_provider("bedrock", _FakeSettings())
    assert isinstance(provider, BedrockProvider)
    assert provider.model_id.startswith("anthropic.")


def test_create_model_provider_ollama() -> None:
    provider = create_model_provider("ollama", _FakeSettings())
    assert isinstance(provider, OllamaProvider)


def test_create_payslip_parser_uses_model_provider() -> None:
    from payroll_copilot.infrastructure.ai.payslip_parser_factory import create_payslip_parser
    from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser

    settings = _FakeSettings()
    settings.payslip_parser_model = ""
    settings.payslip_parser_timeout_seconds = 45.0
    settings.payslip_parser_temperature = 0.0
    settings.payslip_parser_use_json_format = True
    settings.payslip_parser_layout_enabled = True
    settings.payslip_parser_max_predict = 4096

    parser = create_payslip_parser(settings)
    assert isinstance(parser, OllamaPayslipParser)
    assert parser._provider is not None  # noqa: SLF001
