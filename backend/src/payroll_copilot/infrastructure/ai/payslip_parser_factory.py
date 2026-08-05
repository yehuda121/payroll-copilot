"""Factory for payslip parser implementations (deterministic PDF/text — no AI)."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.infrastructure.ai.deterministic_payslip_parser import (
    DeterministicPayslipParser,
)
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter


def create_payslip_parser(
    settings: Any,
    *,
    router: AIProviderRouter | None = None,
) -> PayslipParser:
    """Return the shared deterministic payslip parser (AI path disabled)."""
    _ = settings, router
    return DeterministicPayslipParser()
