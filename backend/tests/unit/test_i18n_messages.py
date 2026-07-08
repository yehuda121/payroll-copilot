"""Unit tests for localized user-facing message catalogs."""

from __future__ import annotations

from payroll_copilot.infrastructure.i18n import finding_message, scope_label
from payroll_copilot.infrastructure.i18n.messages import assistant_text


def test_finding_message_localized_for_supported_locales() -> None:
    key = "validation.minimum_wage.below_threshold"
    assert "minimum" in finding_message(key, "en").lower()
    assert "מינימום" in finding_message(key, "he")
    assert "الأدنى" in finding_message(key, "ar")


def test_scope_label_localized() -> None:
    assert scope_label("payroll_rules", "en") == "Payroll Rules"
    assert scope_label("payroll_rules", "he") == "כללי שכר"
    assert scope_label("payroll_rules", "ar") == "قواعد الرواتب"


def test_assistant_greeting_varies_by_locale() -> None:
    he = assistant_text("greeting", "he")
    en = assistant_text("greeting", "en")
    ar = assistant_text("greeting", "ar")
    assert he != en
    assert ar != en
    assert "Payroll Copilot" in en
