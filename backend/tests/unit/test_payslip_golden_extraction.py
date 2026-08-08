"""Golden payslip extraction tests.

Developer workflow:
1. Add ``tests/fixtures/payslips/<case>/input.pdf``
2. Add ``expected.json`` with canonical field expectations
3. Run: ``pytest tests/unit/test_payslip_golden_extraction.py -q``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from payroll_copilot.application.services.company_payslip_extraction.adapter import (
    extract_payslip_document,
)
from payroll_copilot.application.services.deterministic_pdf import (
    DeterministicExtractionStatus,
    extract_document_from_pdf,
)
from payroll_copilot.application.services.dynamic_document import (
    canonical_values_from_structured,
)
from payroll_copilot.domain.enums import DocumentType

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "payslips"


def _discover_cases() -> list[Path]:
    if not FIXTURES_ROOT.is_dir():
        return []
    cases = []
    for path in sorted(FIXTURES_ROOT.iterdir()):
        if not path.is_dir():
            continue
        if (path / "input.pdf").is_file() and (path / "expected.json").is_file():
            cases.append(path)
    return cases


CASES = _discover_cases()


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_golden_payslip_extraction(case_dir: Path) -> None:
    pdf_bytes = (case_dir / "input.pdf").read_bytes()
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))

    # Real deterministic production path — no mocks.
    result = extract_document_from_pdf(
        pdf_bytes,
        document_type=DocumentType.PAYSLIP,
        filename=f"{case_dir.name}.pdf",
        mime_type="application/pdf",
    )
    assert result.status is DeterministicExtractionStatus.COMPLETED, (
        f"{case_dir.name}: extraction status={result.status} error={result.error_code}"
    )

    # Prefer unified canonical projection from Document Model entries
    # (primary paystub only for multi-slip PDFs).
    actual = canonical_values_from_structured(result.structured)
    if not any(actual.get(k) for k in (expected.get("canonical") or {})):
        adapter = extract_payslip_document(pdf_bytes, document_type=DocumentType.PAYSLIP)
        actual = adapter.field_map()

    for key, expected_value in (expected.get("canonical") or {}).items():
        got = actual.get(key)
        assert got == expected_value, (
            f"{case_dir.name}: field {key!r} expected {expected_value!r}, got {got!r}"
        )

    for key, needle in (expected.get("canonical_contains") or {}).items():
        got = str(actual.get(key) or "")
        assert needle in got, (
            f"{case_dir.name}: field {key!r} expected to contain {needle!r}, got {got!r}"
        )

    for key, forbidden in (expected.get("must_not_equal") or {}).items():
        got = actual.get(key)
        assert got != forbidden, (
            f"{case_dir.name}: field {key!r} must not equal {forbidden!r} (got {got!r})"
        )


def test_golden_fixture_cases_discovered() -> None:
    assert CASES, "Expected at least one payslip golden case under tests/fixtures/payslips/"
