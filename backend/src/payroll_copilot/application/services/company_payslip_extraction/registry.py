"""Company extraction profile registry."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.company_payslip_extraction.core.engine import extract_document as _extract_document
from payroll_copilot.application.services.company_payslip_extraction.core.profile import CompanyProfile

_REGISTRY: dict[str, CompanyProfile] = {}


def register(profile: CompanyProfile) -> None:
    _REGISTRY[profile.key] = profile


def get_company(company_key: str) -> CompanyProfile:
    try:
        return _REGISTRY[company_key]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown company_key {company_key!r}. Registered: {known}"
        ) from exc


def list_companies() -> list[str]:
    return sorted(_REGISTRY)


def extract(
    file_bytes: bytes,
    *,
    company_key: str,
    debug_layout: bool = False,
) -> dict[str, Any]:
    """Resolve company profile and run deterministic extraction."""
    profile = get_company(company_key)
    return _extract_document(
        file_bytes,
        profile=profile,
        debug_layout=debug_layout,
    )


def _bootstrap() -> None:
    from payroll_copilot.application.services.company_payslip_extraction.companies.primary_company.profile import PROFILE

    register(PROFILE)


_bootstrap()
