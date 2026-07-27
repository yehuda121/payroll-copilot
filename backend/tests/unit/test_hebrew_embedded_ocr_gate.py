"""Tests for Hebrew script mismatch embedded-text OCR gate."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import fitz
import pytest

from payroll_copilot.application.ports.ocr import OcrPage
from payroll_copilot.infrastructure.ocr.language import tesseract_lang_expects_hebrew
from payroll_copilot.infrastructure.ocr.pdf_text import (
    SCRIPT_MISMATCH_HEBREW_EXPECTED,
    apply_hebrew_script_mismatch_gate,
    assess_embedded_text_quality,
)
from payroll_copilot.infrastructure.ocr.preprocessing import (
    DocumentImagePreprocessor,
    OcrPreprocessingConfig,
)
from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider


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


_LATIN_PAYSLIP = (
    "Employee Name Dana Levi\n"
    "Gross Salary 12000\n"
    "Net salary 9500\n"
    "Department Payroll Operations\n"
    "Pay period January 2020\n"
)

_HEBREW_PAYSLIP = (
    "שם עובד דנה לוי\n"
    "שכר ברוטו 12000\n"
    "שכר נטו 9500\n"
    "מחלקה שכר\n"
    "תקופת שכר ינואר 2020\n"
)


@pytest.mark.parametrize(
    ("tess_lang", "expected"),
    [
        ("heb+eng", True),
        ("heb", True),
        ("eng", False),
        ("ara+eng", False),
        ("eng+ara", False),
        ("", False),
    ],
)
def test_tesseract_lang_expects_hebrew(tess_lang: str, expected: bool) -> None:
    assert tesseract_lang_expects_hebrew(tess_lang) is expected


def test_gate_rejects_hebrew_expected_without_hebrew_letters() -> None:
    pages = [_LATIN_PAYSLIP]
    quality = assess_embedded_text_quality(pages)
    assert quality.usable
    gated = apply_hebrew_script_mismatch_gate(quality, pages, hebrew_expected=True)
    assert not gated.usable
    assert gated.reason == SCRIPT_MISMATCH_HEBREW_EXPECTED


def test_gate_keeps_hebrew_embedded_text() -> None:
    pages = [_HEBREW_PAYSLIP]
    quality = assess_embedded_text_quality(pages)
    assert quality.usable
    gated = apply_hebrew_script_mismatch_gate(quality, pages, hebrew_expected=True)
    assert gated.usable
    assert gated.reason is None


def test_gate_noop_when_hebrew_not_expected() -> None:
    pages = [_LATIN_PAYSLIP]
    quality = assess_embedded_text_quality(pages)
    gated = apply_hebrew_script_mismatch_gate(quality, pages, hebrew_expected=False)
    assert gated.usable
    assert gated.reason is None


def test_gate_preserves_poor_quality_reason() -> None:
    pages = [""]
    quality = assess_embedded_text_quality(pages)
    assert not quality.usable
    gated = apply_hebrew_script_mismatch_gate(quality, pages, hebrew_expected=True)
    assert not gated.usable
    assert gated.reason == quality.reason
    assert gated.reason != SCRIPT_MISMATCH_HEBREW_EXPECTED


@pytest.mark.asyncio
async def test_provider_hebrew_latin_only_falls_through_to_raster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
    )
    pdf = _make_text_pdf(_LATIN_PAYSLIP)
    called = {"raster": 0}

    def _fake_rasterize(content: bytes, **kwargs: Any) -> list[bytes]:
        called["raster"] += 1
        return [b"fakepng"]

    def _fake_extract_image(*args: Any, **kwargs: Any) -> tuple[OcrPage, str | None]:
        return (
            OcrPage(page=1, language="he", text="OCR hebrew fallback text", confidence=0.8, lines=()),
            None,
        )

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        _fake_rasterize,
    )
    monkeypatch.setattr(provider, "_extract_image_sync", _fake_extract_image)

    result = await provider.extract(
        content=pdf,
        media_type="application/pdf",
        filename="slip.pdf",
        language="he",
    )

    assert called["raster"] == 1
    assert result.engine == "tesseract"
    assert f"pdf_embedded_text_insufficient:{SCRIPT_MISMATCH_HEBREW_EXPECTED}" in result.warnings
    assert "pdf_embedded_text_used" not in result.warnings


@pytest.mark.asyncio
async def test_provider_hebrew_with_hebrew_letters_uses_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider()
    # Avoid depending on system fonts for Hebrew glyph embedding in fitz.
    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.extract_embedded_pdf_text",
        lambda _content: ([_HEBREW_PAYSLIP], 1),
    )
    rasterize = MagicMock(side_effect=AssertionError("rasterize should not run"))
    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        rasterize,
    )

    result = await provider.extract(
        content=b"%PDF-hebrew-fixture",
        media_type="application/pdf",
        filename="slip.pdf",
        language="he",
    )

    assert "pdf_text" in result.engine
    assert "pdf_embedded_text_used" in result.warnings
    rasterize.assert_not_called()


@pytest.mark.asyncio
async def test_provider_english_latin_keeps_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider()
    pdf = _make_text_pdf(_LATIN_PAYSLIP)
    rasterize = MagicMock(side_effect=AssertionError("rasterize should not run"))
    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        rasterize,
    )

    result = await provider.extract(
        content=pdf,
        media_type="application/pdf",
        filename="slip.pdf",
        language="en",
    )

    assert "pdf_text" in result.engine
    assert "pdf_embedded_text_used" in result.warnings
    rasterize.assert_not_called()


@pytest.mark.asyncio
async def test_provider_blank_pdf_still_uses_ordinary_insufficient_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
    )
    pdf = _make_blank_pdf()

    def _fake_rasterize(content: bytes, **kwargs: Any) -> list[bytes]:
        return [b"fakepng"]

    def _fake_extract_image(*args: Any, **kwargs: Any) -> tuple[OcrPage, str | None]:
        return (
            OcrPage(page=1, language="he", text="OCR text fallback", confidence=0.8, lines=()),
            None,
        )

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        _fake_rasterize,
    )
    monkeypatch.setattr(provider, "_extract_image_sync", _fake_extract_image)

    result = await provider.extract(
        content=pdf,
        media_type="application/pdf",
        filename="blank.pdf",
        language="he",
    )

    assert any(
        w.startswith("pdf_embedded_text_insufficient:")
        and SCRIPT_MISMATCH_HEBREW_EXPECTED not in w
        for w in result.warnings
    )
