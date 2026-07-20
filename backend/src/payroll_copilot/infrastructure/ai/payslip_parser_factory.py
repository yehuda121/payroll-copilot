"""Factory for payslip AI parser implementations."""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.exceptions import (
    PayslipParserTimeoutError,
    PayslipParserUnavailableError,
)
from payroll_copilot.application.ports import AICapability
from payroll_copilot.application.ports.payslip_parser import PayslipParseResult, PayslipParser
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter

logger = logging.getLogger(__name__)


class FallbackPayslipParser:
    """Try primary extraction provider; on provider outage, try configured fallback."""

    def __init__(
        self,
        primary: PayslipParser,
        fallback: PayslipParser,
        *,
        primary_name: str,
        fallback_name: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    async def parse(self, **kwargs: Any) -> PayslipParseResult:
        try:
            return await self._primary.parse(**kwargs)
        except (PayslipParserUnavailableError, PayslipParserTimeoutError) as exc:
            logger.warning(
                "payslip_extraction_primary_failed provider=%s error=%s; "
                "trying fallback=%s",
                self._primary_name,
                exc,
                self._fallback_name,
            )
            result = await self._fallback.parse(**kwargs)
            warnings = list(result.warnings or [])
            warning = (
                f"provider_fallback_used:{self._primary_name}->{self._fallback_name}"
            )
            if warning not in warnings:
                warnings.append(warning)
            return result.model_copy(update={"warnings": warnings})


def _build_parser(
    settings: Any,
    *,
    model_provider: Any,
    model: str,
) -> OllamaPayslipParser:
    return OllamaPayslipParser(
        model_provider=model_provider,
        model=model,
        timeout_seconds=float(getattr(settings, "payslip_parser_timeout_seconds", 45.0)),
        temperature=float(getattr(settings, "payslip_parser_temperature", 0.0)),
        use_json_format=bool(getattr(settings, "payslip_parser_use_json_format", True)),
        layout_enabled=bool(getattr(settings, "payslip_parser_layout_enabled", True)),
        max_predict=int(getattr(settings, "payslip_parser_max_predict", 4096)),
    )


def create_payslip_parser(
    settings: Any,
    *,
    router: AIProviderRouter | None = None,
) -> PayslipParser:
    """Create the payslip parser backed by the configured ModelProvider.

    Prompts and validation stay in OllamaPayslipParser; transport is Bedrock or Ollama.
    Optional ``payslip_extraction_fallback_provider`` degrades gracefully on outage.
    """
    active_router = router or AIProviderRouter(settings)
    route = active_router.route(AICapability.PAYSLIP_EXTRACTION)
    primary = _build_parser(
        settings,
        model_provider=route.provider,
        model=route.model,
    )

    fallback_name = str(
        getattr(settings, "payslip_extraction_fallback_provider", "") or ""
    ).strip().lower()
    if not fallback_name or fallback_name == route.provider_name:
        return primary

    try:
        fallback_route = active_router.route_provider(
            AICapability.PAYSLIP_EXTRACTION,
            fallback_name,
        )
        fallback = _build_parser(
            settings,
            model_provider=fallback_route.provider,
            model=fallback_route.model,
        )
    except Exception as exc:  # noqa: BLE001 — misconfig must not break primary
        logger.warning(
            "payslip_extraction_fallback_unavailable provider=%s error=%s",
            fallback_name,
            exc,
        )
        return primary

    return FallbackPayslipParser(
        primary,
        fallback,
        primary_name=route.provider_name,
        fallback_name=fallback_route.provider_name,
    )
