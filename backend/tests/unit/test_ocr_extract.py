"""Unit tests for Phase 1 OCR extraction (fake providers — no Paddle runtime required)."""

from __future__ import annotations

from typing import Any

import pytest

from payroll_copilot.application.exceptions import (
    OcrEmptyDocumentError,
    OcrLanguageNotSupportedError,
    OcrTimeoutError,
    OcrUnsupportedFileError,
)
from payroll_copilot.application.ocr_input import normalize_document_language, resolve_media_type
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
    ExtractDocumentTextUseCase,
)
from payroll_copilot.infrastructure.ocr.confidence import average_confidence, normalize_paddle_score
from payroll_copilot.infrastructure.ocr.factory import HEBREW_FALLBACK_WARNING, RoutingOCRProvider
from payroll_copilot.infrastructure.ocr.language import to_paddle_lang

# Minimal valid 1x1 PNG (no Pillow required).
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeProvider:
    def __init__(self, engine: str) -> None:
        self.engine_name = engine
        self.calls: list[dict[str, Any]] = []

    async def extract(
        self,
        *,
        content: bytes,
        media_type: str,
        filename: str | None = None,
        language: str = "auto",
    ) -> OCRResult:
        self.calls.append(
            {
                "content": content,
                "media_type": media_type,
                "filename": filename,
                "language": language,
            }
        )
        page = OcrPage(
            page=1,
            language=language,
            text=f"text-from-{self.engine_name}",
            confidence=0.91,
            lines=(OcrLine(text=f"text-from-{self.engine_name}", confidence=0.91),),
        )
        return OCRResult(
            pages=(page,),
            engine=self.engine_name,
            language_requested=language,
            language_effective=language,
            raw_text=page.text,
            overall_confidence=0.91,
            fields=(),
            warnings=(),
        )


def test_resolve_media_type_from_extension() -> None:
    assert resolve_media_type(filename="a.PDF", content_type=None) == "application/pdf"
    assert resolve_media_type(filename="x.jpg", content_type=None) == "image/jpeg"


def test_resolve_media_type_rejects_unsupported() -> None:
    with pytest.raises(OcrUnsupportedFileError):
        resolve_media_type(filename="notes.docx", content_type="application/msword")


def test_average_confidence_none_when_empty() -> None:
    assert average_confidence([]) is None
    assert average_confidence([0.5, 1.0]) == 0.75


def test_normalize_paddle_score() -> None:
    assert normalize_paddle_score(0.88) == 0.88
    assert normalize_paddle_score(88) == 0.88
    assert normalize_paddle_score("bad") is None


def test_hebrew_maps_blocked_for_paddle() -> None:
    normalize_document_language("he")
    with pytest.raises(OcrLanguageNotSupportedError):
        to_paddle_lang("he")


@pytest.mark.asyncio
async def test_routing_hebrew_uses_tesseract_and_warns() -> None:
    primary = _FakeProvider("paddleocr")
    fallback = _FakeProvider("tesseract")
    router = RoutingOCRProvider(primary=primary, hebrew_fallback=fallback)

    result = await router.extract(
        content=_PNG_1X1,
        media_type="image/png",
        filename="slip.png",
        language="he",
    )

    assert result.engine == "tesseract"
    assert HEBREW_FALLBACK_WARNING in result.warnings
    assert fallback.calls and not primary.calls
    assert result.overall_confidence == 0.91


@pytest.mark.asyncio
async def test_routing_auto_uses_tesseract_for_israeli_payslips() -> None:
    primary = _FakeProvider("paddleocr")
    fallback = _FakeProvider("tesseract")
    router = RoutingOCRProvider(primary=primary, hebrew_fallback=fallback)

    result = await router.extract(
        content=_PNG_1X1,
        media_type="image/png",
        filename="slip.png",
        language="auto",
    )

    assert result.engine == "tesseract"
    assert fallback.calls and not primary.calls
    assert any("heb+eng" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_routing_english_uses_paddle() -> None:
    primary = _FakeProvider("paddleocr")
    fallback = _FakeProvider("tesseract")
    router = RoutingOCRProvider(primary=primary, hebrew_fallback=fallback)

    result = await router.extract(
        content=_PNG_1X1,
        media_type="image/png",
        filename="slip.png",
        language="en",
    )

    assert result.engine == "paddleocr"
    assert primary.calls and not fallback.calls
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_extract_use_case_empty_document() -> None:
    use_case = ExtractDocumentTextUseCase(_FakeProvider("paddleocr"), timeout_seconds=5)
    with pytest.raises(OcrEmptyDocumentError):
        await use_case.execute(
            ExtractDocumentTextCommand(
                content=b"",
                filename="a.png",
                content_type="image/png",
                language="en",
            )
        )


@pytest.mark.asyncio
async def test_extract_use_case_timeout() -> None:
    class _Slow(_FakeProvider):
        async def extract(self, **kwargs: Any) -> OCRResult:  # type: ignore[override]
            import asyncio

            await asyncio.sleep(0.05)
            return await super().extract(**kwargs)

    use_case = ExtractDocumentTextUseCase(_Slow("paddleocr"), timeout_seconds=0.01)
    with pytest.raises(OcrTimeoutError):
        await use_case.execute(
            ExtractDocumentTextCommand(
                content=_PNG_1X1,
                filename="a.png",
                content_type="image/png",
                language="en",
            )
        )


@pytest.mark.asyncio
async def test_extract_use_case_success() -> None:
    use_case = ExtractDocumentTextUseCase(_FakeProvider("paddleocr"), timeout_seconds=5)
    result = await use_case.execute(
        ExtractDocumentTextCommand(
            content=_PNG_1X1,
            filename="a.png",
            content_type="image/png",
            language="en",
        )
    )
    assert result.engine == "paddleocr"
    assert result.pages[0].text.startswith("text-from")
    assert result.overall_confidence == 0.91


def test_corrupt_pdf_raises() -> None:
    pytest.importorskip("fitz")
    from payroll_copilot.application.exceptions import OcrCorruptedDocumentError
    from payroll_copilot.infrastructure.ocr.pdf_rasterizer import rasterize_pdf_to_png_pages

    with pytest.raises(OcrCorruptedDocumentError):
        rasterize_pdf_to_png_pages(b"%PDF-not-a-real-file")
