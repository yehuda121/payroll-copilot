"""Stable development-only user ↔ employee binding constants.

Used by auth/dev session issuance and binding bootstrap — never by frontend hardcoding
of employee UUIDs for authorization decisions.
"""

from __future__ import annotations

from uuid import UUID

from payroll_copilot.application.use_cases.seed_accountant_portal import (
    SEED_NAMESPACE,
    deterministic_employee_id,
)
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)

# Fixed auth user id for local employee portal testing.
DEV_EMPLOYEE_USER_ID = UUID("00000000-0000-4000-8000-000000000101")
DEV_EMPLOYEE_USER_EMAIL = "sarah.cohen@dev.payroll-copilot.local"

# Seed employee #5 — Yehuda Shmulovitz (שמולביץ יהודה), national ID 313366783.
DEV_EMPLOYEE_SEED_NATIONAL_ID = "313366783"
DEV_EMPLOYEE_NUMBER = "5"


def get_dev_bound_employee_id() -> UUID:
    return deterministic_employee_id(DEV_EMPLOYEE_SEED_NATIONAL_ID)


__all__ = [
    "DEMO_ORGANIZATION_ID",
    "DEV_EMPLOYEE_USER_ID",
    "DEV_EMPLOYEE_USER_EMAIL",
    "DEV_EMPLOYEE_SEED_NATIONAL_ID",
    "DEV_EMPLOYEE_NUMBER",
    "SEED_NAMESPACE",
    "get_dev_bound_employee_id",
]
