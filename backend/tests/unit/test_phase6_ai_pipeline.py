"""Phase 6 AI pipeline hardening — confidence, trust tiers, fallback, plausibility."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from payroll_copilot.application.exceptions import PayslipParserUnavailableError
from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    FieldTrustTier,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.confidence_normalize import (
    normalize_unit_interval_confidence,
)
from payroll_copilot.application.services.parser_evidence import (
    apply_plausibility_checks,
    derive_trust_tier,
)
from payroll_copilot.infrastructure.ai.payslip_parser_factory import (
    FallbackPayslipParser,
    create_payslip_parser,
)


def _parse(**overrides: ExtractedField) -> StructuredPayslipParse:
    data = StructuredPayslipParse().model_dump()
    for key, field in overrides.items():
        data[key] = field.model_dump()
    return StructuredPayslipParse.model_validate(data)


def test_normalize_confidence_accepts_percent_scale():
    assert normalize_unit_interval_confidence(95) == pytest.approx(0.95)
    assert normalize_unit_interval_confidence("87.5") == pytest.approx(0.875)
    assert normalize_unit_interval_confidence(0.42) == pytest.approx(0.42)
    assert normalize_unit_interval_confidence("high") == pytest.approx(0.9)
    assert normalize_unit_interval_confidence(1.5) is None
    assert normalize_unit_interval_confidence(101) is None
    assert normalize_unit_interval_confidence(-1) is None


def test_extracted_field_coerces_percent_confidence():
    field = ExtractedField(
        value=100,
        status=FieldExtractionStatus.FOUND,
        confidence=95,
        source_text="100",
    )
    assert field.confidence == pytest.approx(0.95)


def test_trust_tier_ocr_verified_from_source_text():
    field = ExtractedField(
        value="יהודה",
        status=FieldExtractionStatus.FOUND,
        source_text="יהודה",
        parser_method="semantic_llm",
    )
    assert derive_trust_tier(field) == FieldTrustTier.OCR_VERIFIED


def test_trust_tier_ai_inferred_without_evidence():
    field = ExtractedField(
        value=12000,
        status=FieldExtractionStatus.FOUND,
        parser_method="semantic_llm",
    )
    assert derive_trust_tier(field) == FieldTrustTier.AI_INFERRED


def test_plausibility_assigns_trust_tiers():
    result = apply_plausibility_checks(
        _parse(
            employee_name=ExtractedField(
                value="יהודה שמולביץ",
                status=FieldExtractionStatus.FOUND,
                confidence=0.9,
                source_text="יהודה שמולביץ",
            )
        )
    )
    assert result.employee_name.trust_tier == FieldTrustTier.OCR_VERIFIED
    assert result.gross_salary.trust_tier == FieldTrustTier.UNKNOWN


def test_implausible_pay_period_month():
    result = apply_plausibility_checks(
        _parse(
            pay_period=ExtractedField(
                value="13/2024",
                status=FieldExtractionStatus.FOUND,
                confidence=0.9,
                source_text="13/2024",
            )
        )
    )
    assert result.pay_period.status == FieldExtractionStatus.UNCERTAIN
    assert "implausible_pay_period_month" in result.pay_period.warnings
    assert result.pay_period.value == "13/2024"


def test_implausible_employee_id_length():
    result = apply_plausibility_checks(
        _parse(
            employee_id=ExtractedField(
                value="12",
                status=FieldExtractionStatus.FOUND,
                confidence=0.9,
                source_text="12",
            )
        )
    )
    assert result.employee_id.status == FieldExtractionStatus.UNCERTAIN
    assert "implausible_employee_id_length" in result.employee_id.warnings


def test_implausible_hours_and_absurd_money():
    result = apply_plausibility_checks(
        _parse(
            regular_hours=ExtractedField(
                value=900,
                status=FieldExtractionStatus.FOUND,
                confidence=0.8,
                source_text="900",
            ),
            gross_salary=ExtractedField(
                value=99_000_000,
                status=FieldExtractionStatus.FOUND,
                confidence=0.8,
                source_text="99000000",
            ),
        )
    )
    assert result.regular_hours.status == FieldExtractionStatus.UNCERTAIN
    assert "implausible_hours_value" in result.regular_hours.warnings
    assert result.gross_salary.status == FieldExtractionStatus.UNCERTAIN
    assert "absurd_money_amount" in result.gross_salary.warnings


@pytest.mark.asyncio
async def test_fallback_parser_uses_secondary_on_unavailable():
    primary = AsyncMock(
        side_effect=PayslipParserUnavailableError("primary down")
    )
    fallback_result = PayslipParseResult(
        model="fallback-model",
        fields=StructuredPayslipParse(),
        warnings=[],
    )
    fallback = AsyncMock(return_value=fallback_result)
    wrapper = FallbackPayslipParser(
        SimpleNamespace(parse=primary),
        SimpleNamespace(parse=fallback),
        primary_name="openai",
        fallback_name="ollama",
    )
    result = await wrapper.parse(ocr_text="hello")
    assert "provider_fallback_used:openai->ollama" in result.warnings
    fallback.assert_awaited_once()


def test_create_payslip_parser_without_fallback_returns_primary_only():
    built: list[str] = []

    class _Prov:
        embedding_dimensions = 3

        async def complete(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def complete_structured(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def embed(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

    def builder(name: str):
        def build(_settings, model):
            built.append(name)
            return _Prov()

        return build

    from payroll_copilot.infrastructure.ai.provider_router import (
        AIProviderRouter,
        ProviderRegistration,
    )

    settings = SimpleNamespace(
        model_provider="bedrock",
        payslip_extraction_provider="openai",
        payslip_extraction_fallback_provider="",
        document_extraction_provider="",
        assistant_provider="",
        employee_chat_provider="",
        accountant_chat_provider="",
        rag_provider="",
        embeddings_provider="",
        general_provider="",
        payslip_parser_model="m1",
        payslip_parser_timeout_seconds=30.0,
        payslip_parser_temperature=0.0,
        payslip_parser_use_json_format=True,
        payslip_parser_layout_enabled=True,
        payslip_parser_max_predict=1024,
        openai_model="gpt-5",
        ollama_default_model="local",
        bedrock_model_id="b1",
    )
    router = AIProviderRouter(
        settings,
        provider_registry={
            "openai": ProviderRegistration(builder("openai"), "openai_model", "gpt-5"),
            "ollama": ProviderRegistration(
                builder("ollama"), "ollama_default_model", "local"
            ),
            "bedrock": ProviderRegistration(
                builder("bedrock"), "bedrock_model_id", ""
            ),
        },
    )
    parser = create_payslip_parser(settings, router=router)
    assert not isinstance(parser, FallbackPayslipParser)
    assert built == ["openai"]


def test_create_payslip_parser_wraps_fallback_when_configured():
    built: list[str] = []

    class _Prov:
        embedding_dimensions = 3

        async def complete(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def complete_structured(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def embed(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

    def builder(name: str):
        def build(_settings, model):
            built.append(name)
            return _Prov()

        return build

    from payroll_copilot.infrastructure.ai.provider_router import (
        AIProviderRouter,
        ProviderRegistration,
    )

    settings = SimpleNamespace(
        model_provider="bedrock",
        payslip_extraction_provider="openai",
        payslip_extraction_fallback_provider="ollama",
        document_extraction_provider="",
        assistant_provider="",
        employee_chat_provider="",
        accountant_chat_provider="",
        rag_provider="",
        embeddings_provider="",
        general_provider="",
        payslip_parser_model="",
        payslip_parser_timeout_seconds=30.0,
        payslip_parser_temperature=0.0,
        payslip_parser_use_json_format=True,
        payslip_parser_layout_enabled=True,
        payslip_parser_max_predict=1024,
        openai_model="gpt-5",
        ollama_default_model="local",
        bedrock_model_id="b1",
        openai_api_key="",
        openai_embedding_model="text-embedding-3-small",
        openai_embedding_dimensions=1536,
        openai_timeout_seconds=120.0,
        openai_max_retries=0,
        openai_reasoning_effort="minimal",
        openai_base_url="",
        ollama_embedding_model="nomic-embed-text",
    )
    router = AIProviderRouter(
        settings,
        provider_registry={
            "openai": ProviderRegistration(builder("openai"), "openai_model", "gpt-5"),
            "ollama": ProviderRegistration(
                builder("ollama"), "ollama_default_model", "local"
            ),
            "bedrock": ProviderRegistration(
                builder("bedrock"), "bedrock_model_id", ""
            ),
        },
    )
    parser = create_payslip_parser(settings, router=router)
    assert isinstance(parser, FallbackPayslipParser)
    assert set(built) == {"openai", "ollama"}
