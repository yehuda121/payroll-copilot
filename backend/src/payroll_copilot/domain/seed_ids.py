"""Stable seed / demo identity constants (framework-independent).

Kept in domain so binding helpers and application seeders share one source
without domain importing application modules.
"""

from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_URL

# Fixed demo organization used for local guest / seed flows.
DEMO_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000001")

SEED_NAMESPACE = uuid5(NAMESPACE_URL, "payroll-copilot:accountant-portal-seed")


def deterministic_employee_id(national_id: str) -> UUID:
    return uuid5(
        SEED_NAMESPACE,
        f"employee:{''.join(ch for ch in national_id if ch.isalnum())}",
    )


def deterministic_document_id(document_key: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"document:{document_key}")
