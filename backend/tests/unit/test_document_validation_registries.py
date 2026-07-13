"""Tests for extensible document-type and validation-module registries."""

from payroll_copilot.domain.document_types import (
    DocumentTypeDefinition,
    ExpectedDocumentAvailability,
    get_document_type,
    list_document_types,
    register_document_type,
)
from payroll_copilot.domain.validation_modules import (
    ValidationModuleDefinition,
    get_validation_module,
    list_validation_modules,
    register_validation_module,
)


def test_builtin_document_types_registered() -> None:
    keys = {item.key for item in list_document_types()}
    assert "payslip" in keys
    assert "attendance" in keys
    assert "contract" in keys
    assert "national_id" in keys


def test_register_future_document_type_without_redesign() -> None:
    key = "future_tax_form_test"
    register_document_type(
        DocumentTypeDefinition(
            key=key,
            label="Future Tax Form",
            category="tax",
            supports_period=True,
            collection_key="tax",
            sort_order=90,
        )
    )
    assert get_document_type(key) is not None
    assert any(item.key == key for item in list_document_types())


def test_expected_availability_vocabulary() -> None:
    values = {item.value for item in ExpectedDocumentAvailability}
    assert values == {
        "available",
        "missing",
        "processing",
        "failed",
        "needs_review",
        "versioned",
    }


def test_validation_modules_are_pluggable() -> None:
    modules = {item.key for item in list_validation_modules()}
    assert "payroll" in modules
    assert "attendance" in modules
    assert "company_custom" in modules
    register_validation_module(
        ValidationModuleDefinition(
            key="future_module_test",
            label="Future Module",
            description="Extensibility check",
            supported_document_types=("payslip",),
        )
    )
    assert get_validation_module("future_module_test") is not None
