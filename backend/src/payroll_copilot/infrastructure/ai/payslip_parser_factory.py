"""Factory for payslip AI parser implementations."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.infrastructure.ai.ollama_provider import create_model_provider
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser


def create_payslip_parser(settings: Any) -> PayslipParser:
    """Create the payslip parser backed by the configured ModelProvider.

    Prompts and validation stay in OllamaPayslipParser; transport is Bedrock or Ollama.
    """
    provider_name = getattr(settings, "model_provider", "bedrock").strip().lower()
    model_provider = create_model_provider(provider_name, settings)

    if provider_name == "bedrock":
        model = (
            getattr(settings, "payslip_parser_model", None)
            or getattr(settings, "bedrock_model_id", None)
            or ""
        )
    else:
        model = getattr(settings, "payslip_parser_model", None) or settings.ollama_default_model

    return OllamaPayslipParser(
        model_provider=model_provider,
        model=model,
        timeout_seconds=float(getattr(settings, "payslip_parser_timeout_seconds", 45.0)),
        temperature=float(getattr(settings, "payslip_parser_temperature", 0.0)),
        use_json_format=bool(getattr(settings, "payslip_parser_use_json_format", True)),
        layout_enabled=bool(getattr(settings, "payslip_parser_layout_enabled", True)),
        max_predict=int(getattr(settings, "payslip_parser_max_predict", 4096)),
    )
