"""Factory for payslip AI parser implementations."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser
from payroll_copilot.infrastructure.config.ollama_resolver import get_resolved_ollama_base_url


def create_payslip_parser(settings: Any) -> PayslipParser:
    """Create the configured payslip parser (Ollama by default)."""
    provider = getattr(settings, "model_provider", "ollama").strip().lower()
    if provider != "ollama":
        msg = f"Unsupported payslip parser provider: {provider}"
        raise ValueError(msg)

    model = getattr(settings, "payslip_parser_model", None) or settings.ollama_default_model
    return OllamaPayslipParser(
        base_url=get_resolved_ollama_base_url(settings),
        model=model,
        timeout_seconds=float(getattr(settings, "payslip_parser_timeout_seconds", 180.0)),
        temperature=float(getattr(settings, "payslip_parser_temperature", 0.0)),
        use_json_format=bool(getattr(settings, "payslip_parser_use_json_format", True)),
        layout_enabled=bool(getattr(settings, "payslip_parser_layout_enabled", True)),
    )
