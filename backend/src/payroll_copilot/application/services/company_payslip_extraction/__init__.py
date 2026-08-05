"""Company-aware deterministic payslip extraction (pdfplumber + layout rules).

Architecture:
  - ``core`` — shared extraction engine
  - ``companies/<key>`` — company-specific profile configuration
  - ``registry`` — selects the company profile
  - ``adapter`` — maps extractor output into Payroll Copilot Document Model types

No LLM participates in this path.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.company_payslip_extraction.registry import (
    extract,
    get_company,
    list_companies,
    register,
)

DEFAULT_COMPANY_KEY = "primary_company"

__all__ = [
    "COMPANY_PAYSLIP_ENGINE",
    "COMPANY_PAYSLIP_EXTRACTOR_VERSION",
    "DEFAULT_COMPANY_KEY",
    "extract",
    "extract_payslip_document",
    "get_company",
    "list_companies",
    "paystub_entries_to_dynamic_entries",
    "paystub_entries_to_normalized_fields",
    "register",
]

_ADAPTER_EXPORTS = frozenset(
    {
        "COMPANY_PAYSLIP_ENGINE",
        "COMPANY_PAYSLIP_EXTRACTOR_VERSION",
        "extract_payslip_document",
        "paystub_entries_to_dynamic_entries",
        "paystub_entries_to_normalized_fields",
    }
)


def __getattr__(name: str) -> Any:
    if name in _ADAPTER_EXPORTS:
        from payroll_copilot.application.services.company_payslip_extraction import adapter as _adapter

        return getattr(_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
