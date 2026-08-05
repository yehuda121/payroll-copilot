"""Deterministic PayslipParser — company-aware line extraction from OCR/PDF text (no AI)."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    FieldTrustTier,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.company_payslip_extraction import (
    COMPANY_PAYSLIP_EXTRACTOR_VERSION,
    DEFAULT_COMPANY_KEY,
    get_company,
    paystub_entries_to_normalized_fields,
)
from payroll_copilot.application.services.company_payslip_extraction.core.engine import (
    build_payslip_from_lines,
    clean_line,
    split_payslips,
)
from payroll_copilot.application.services.company_payslip_extraction.core.profile import (
    use_profile,
)
from payroll_copilot.application.services.text_normalize import normalize_extracted_text


class DeterministicPayslipParser:
    """Implements PayslipParser using the company payslip line engine (no LLM)."""

    def __init__(self, *, company_key: str = DEFAULT_COMPANY_KEY) -> None:
        self._company_key = company_key

    async def parse(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
        **kwargs: Any,
    ) -> PayslipParseResult:
        _ = kwargs
        text = normalize_extracted_text(ocr_text or "")
        if pages_text:
            joined = "\n".join(normalize_extracted_text(p or "") for p in pages_text)
            if joined.strip():
                text = joined

        profile = get_company(self._company_key)
        lines = [clean_line(ln) for ln in text.splitlines() if clean_line(ln)]
        with use_profile(profile):
            blocks = split_payslips(lines, profile=profile)
            if not blocks and lines:
                blocks = [lines]
            paystubs = [
                build_payslip_from_lines(index, block)
                for index, block in enumerate(blocks, start=1)
            ]

        fields = paystub_entries_to_normalized_fields(paystubs)
        structured = StructuredPayslipParse(language=language)
        additional: dict[str, ExtractedField] = {}
        known = set(StructuredPayslipParse.model_fields) - {
            "additional_fields",
            "parser_notes",
            "language",
        }
        for item in fields:
            extracted = ExtractedField(
                value=item.value,
                confidence=item.confidence,
                source_text=item.source_text,
                status=FieldExtractionStatus.FOUND,
                source_page=item.page,
                parser_method="company_payslip_lines",
                trust_tier=FieldTrustTier.DETERMINISTIC,
            )
            if item.key in known:
                setattr(structured, item.key, extracted)
            else:
                additional[item.key] = extracted
        structured.additional_fields = additional
        return PayslipParseResult(
            fields=structured,
            model=COMPANY_PAYSLIP_EXTRACTOR_VERSION,
            language=language,
            retry_used=False,
            warnings=[],
        )
