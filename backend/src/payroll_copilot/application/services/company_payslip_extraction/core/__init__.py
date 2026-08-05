"""Shared deterministic extraction core."""

from __future__ import annotations

from payroll_copilot.application.services.company_payslip_extraction.core.engine import extract_document
from payroll_copilot.application.services.company_payslip_extraction.core.profile import CompanyProfile, activate_profile, use_profile

__all__ = [
    "CompanyProfile",
    "activate_profile",
    "extract_document",
    "use_profile",
]
