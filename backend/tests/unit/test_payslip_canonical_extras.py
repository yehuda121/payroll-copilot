"""Alias / canonical mapping for newly approved payslip concepts."""

from __future__ import annotations

from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    map_dynamic_entries_to_structured,
    resolve_canonical_key,
)


def test_resolve_new_canonical_aliases() -> None:
    assert resolve_canonical_key("תעודת זהות") == "national_id"
    assert resolve_canonical_key("שם מעסיק") == "employer_name"
    assert resolve_canonical_key("תיק ניכויים") == "employer_id"
    assert resolve_canonical_key("התחלת עבודה") == "employment_start_date"
    assert resolve_canonical_key("ותק שנים") == "seniority_years"
    assert resolve_canonical_key("היקף משרה") == "employment_scope"
    assert resolve_canonical_key("סכום ששולם בפועל") == "amount_paid"
    assert resolve_canonical_key("מינימום לחודש") == "minimum_wage_monthly"
    assert resolve_canonical_key("מינימום לשעה") == "minimum_wage_hourly"
    assert resolve_canonical_key("סניף") == "bank_branch"
    assert resolve_canonical_key("מספר חשבון") == "bank_account"


def test_amount_paid_not_confused_with_line_item_column() -> None:
    # "סכום לתשלום" is commonly a table column header — do not force to amount_paid.
    assert resolve_canonical_key("סכום לתשלום") is None


def test_national_id_aliases_not_employee_id() -> None:
    assert resolve_canonical_key("national id") == "national_id"
    assert resolve_canonical_key("employee id") == "employee_id"
    assert resolve_canonical_key("מספר עובד") == "employee_number"


def test_map_extras_preserve_dynamic_and_project_additional() -> None:
    entries = [
        DynamicDocumentEntry(id="1", key="תעודת זהות", value="313366783", confidence=0.9),
        DynamicDocumentEntry(id="2", key="שם מעסיק", value="Demo Ltd", confidence=0.8),
        DynamicDocumentEntry(id="3", key="סכום ששולם בפועל", value=5000, confidence=0.7),
        DynamicDocumentEntry(id="4", key="custom bonus line", value=10, confidence=0.6),
    ]
    structured, warnings = map_dynamic_entries_to_structured(entries)
    additional = structured["additional_fields"]
    assert additional["national_id"]["value"] == "313366783"
    assert additional["employer_name"]["value"] == "Demo Ltd"
    assert additional["amount_paid"]["value"] == 5000
    assert any("custom" in key or "bonus" in key for key in additional)
    assert "unmapped_label:custom bonus line" in warnings
    # Core keys still present as MISSING placeholders.
    assert structured["net_salary"]["status"] == "MISSING"
