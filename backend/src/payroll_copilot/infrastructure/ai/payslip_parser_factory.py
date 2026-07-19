"""Factory for payslip AI parser implementations."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports import AICapability
from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter


def create_payslip_parser(
    settings: Any,
    *,
    router: AIProviderRouter | None = None,
) -> PayslipParser:
    """Create the payslip parser backed by the configured ModelProvider.

    Prompts and validation stay in OllamaPayslipParser; transport is Bedrock or Ollama.
    """
    route = (router or AIProviderRouter(settings)).route(
        AICapability.PAYSLIP_EXTRACTION
    )

    return OllamaPayslipParser(
        model_provider=route.provider,
        model=route.model,
        timeout_seconds=float(getattr(settings, "payslip_parser_timeout_seconds", 45.0)),
        temperature=float(getattr(settings, "payslip_parser_temperature", 0.0)),
        use_json_format=bool(getattr(settings, "payslip_parser_use_json_format", True)),
        layout_enabled=bool(getattr(settings, "payslip_parser_layout_enabled", True)),
        max_predict=int(getattr(settings, "payslip_parser_max_predict", 4096)),
    )
