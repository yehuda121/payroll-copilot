"""Unit tests for deterministic payslip boundary detection."""

from __future__ import annotations

import fitz
import pytest

from payroll_copilot.application.services.payslip_boundary_detector import (
    PayslipBoundaryDetector,
)


def _pdf_from_pages(page_texts: list[str]) -> bytes:
    """Build a text PDF. Prefer Latin anchors — default fonts may mangle Hebrew."""
    document = fitz.open()
    try:
        for text in page_texts:
            page = document.new_page()
            y = 72
            for line in text.split("\n"):
                page.insert_text((72, y), line)
                y += 14
        return document.tobytes()
    finally:
        document.close()


def _blank_pages(count: int) -> bytes:
    document = fitz.open()
    try:
        for _ in range(count):
            document.new_page()
        return document.tobytes()
    finally:
        document.close()


def test_groups_high_confidence_continuation_pages() -> None:
    pdf_bytes = _pdf_from_pages(
        [
            "\n".join(
                [
                    "Payslip",
                    "Employee Number: EMP-100",
                    "Name: Israel Israeli",
                    "National ID 123456782",
                    "Gross 10000",
                ]
            ),
            "\n".join(
                [
                    "Continued",
                    "Deductions detail",
                    "Tax 1200",
                    "Insurance 400",
                ]
            ),
            "\n".join(
                [
                    "Payslip",
                    "Employee Number: EMP-200",
                    "Name: Dana Cohen",
                    "National ID 234567890",
                    "Net 8000",
                ]
            ),
        ]
    )

    result = PayslipBoundaryDetector().detect(pdf_bytes)

    assert result.strategy.startswith("text_anchor")
    assert [list(b.page_indices) for b in result.boundaries] == [[0, 1], [2]]
    assert result.boundaries[0].page_start == 1
    assert result.boundaries[0].page_end == 2
    assert result.boundaries[0].confidence >= 0.85
    assert result.boundaries[1].page_indices == (2,)


def test_never_merges_low_confidence_pages() -> None:
    pdf_bytes = _pdf_from_pages(
        [
            "\n".join(
                [
                    "Payslip",
                    "Employee Number: EMP-1",
                    "Base salary",
                ]
            ),
            # Ambiguous page: no continuation marker, no identity, weak signal only.
            "\n".join(
                [
                    "Hours table",
                    "Regular 160",
                    "Overtime 12",
                    "General notes for employees",
                ]
            ),
        ]
    )

    result = PayslipBoundaryDetector().detect(pdf_bytes)

    assert [list(b.page_indices) for b in result.boundaries] == [[0], [1]]
    assert all(len(b.page_indices) == 1 for b in result.boundaries)


def test_scanned_package_falls_back_to_one_page_per_slip() -> None:
    result = PayslipBoundaryDetector().detect(_blank_pages(4))

    assert result.strategy == "one_page_fallback"
    assert "split_ambiguous" in result.warnings
    assert [list(b.page_indices) for b in result.boundaries] == [[0], [1], [2], [3]]


@pytest.mark.asyncio
async def test_detect_async_uses_ai_only_when_deterministic_needs_it() -> None:
    detector = PayslipBoundaryDetector()
    # Usable text but no anchors → needs_ai path.
    pdf_bytes = _pdf_from_pages(
        [
            "Monthly payroll package page one with enough printable text content here",
            "Monthly payroll package page two with enough printable text content here",
        ]
    )

    calls: list[tuple] = []

    async def fake_ai(page_texts, page_count):
        calls.append((list(page_texts), page_count))
        return [
            {
                "page_start": 1,
                "page_end": 2,
                "confidence": 0.95,
                "employee_number_hint": "E1",
            }
        ]

    result = await detector.detect_async(pdf_bytes, ai_splitter=fake_ai)

    assert calls, "AI splitter should be invoked when deterministic anchors are missing"
    assert result.strategy == "ai"
    assert [list(b.page_indices) for b in result.boundaries] == [[0, 1]]


@pytest.mark.asyncio
async def test_detect_async_rejects_low_confidence_ai_merge() -> None:
    detector = PayslipBoundaryDetector()
    pdf_bytes = _pdf_from_pages(
        [
            "Monthly payroll package page one with enough printable text content here",
            "Monthly payroll package page two with enough printable text content here",
        ]
    )

    async def low_confidence_ai(_page_texts, _page_count):
        return [
            {
                "page_start": 1,
                "page_end": 2,
                "confidence": 0.4,
            }
        ]

    result = await detector.detect_async(pdf_bytes, ai_splitter=low_confidence_ai)

    assert result.strategy == "one_page_fallback"
    assert [list(b.page_indices) for b in result.boundaries] == [[0], [1]]
