"""Tests for PDF embedded text helpers and extraction diagnostics."""

from __future__ import annotations

import fitz

from payroll_copilot.infrastructure.ocr.pdf_text import (
    embedded_text_is_usable,
    extract_embedded_pdf_text,
)


def _make_text_pdf(text: str, *, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_blank_pdf(*, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def test_embedded_text_extracted_from_text_pdf() -> None:
    pdf = _make_text_pdf("Employee Name Dana Levi\nBase salary 12000\nNet salary 9500")
    pages, count = extract_embedded_pdf_text(pdf)
    assert count == 1
    assert embedded_text_is_usable(pages)
    assert "Dana" in pages[0]
    assert sum(len(p.strip()) for p in pages) > 20


def test_multi_page_pdf_embedded_text() -> None:
    pdf = _make_text_pdf("Page content with enough characters for usability checks.", pages=3)
    pages, count = extract_embedded_pdf_text(pdf)
    assert count == 3
    assert len(pages) == 3
    assert embedded_text_is_usable(pages)


def test_blank_pdf_not_usable_for_embedded_text() -> None:
    pdf = _make_blank_pdf(pages=2)
    pages, count = extract_embedded_pdf_text(pdf)
    assert count == 2
    assert not embedded_text_is_usable(pages)
