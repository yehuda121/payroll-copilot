"""Unit tests for fixture document loader security."""

from __future__ import annotations

import pytest

from payroll_copilot.application.services.fixture_document_loader import (
    FixtureAccessError,
    list_fixture_documents,
    resolve_fixture,
)


def test_list_fixture_documents_includes_expected_groups() -> None:
    grouped = list_fixture_documents()
    assert "valid" in grouped
    assert "invalid" in grouped
    assert isinstance(grouped["valid"], list)
    assert isinstance(grouped["invalid"], list)


def test_resolve_fixture_rejects_path_traversal() -> None:
    with pytest.raises(FixtureAccessError) as exc:
        resolve_fixture("valid/../invalid/payslips_invalid_2026_07_multi.pdf")
    assert exc.value.code in {"invalid_fixture_id", "path_traversal", "fixture_not_found"}


def test_resolve_fixture_unknown_group() -> None:
    with pytest.raises(FixtureAccessError) as exc:
        resolve_fixture("secret/sample.pdf")
    assert exc.value.code == "invalid_fixture_group"
