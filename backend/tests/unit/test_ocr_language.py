"""Unit tests for OCR document-language → Tesseract pack mapping."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from payroll_copilot.application.exceptions import OcrLanguageNotSupportedError
from payroll_copilot.application.ocr_input import normalize_document_language
from payroll_copilot.infrastructure.ocr.language import (
    DEFAULT_TESSERACT_MULTI_LANG,
    TESSERACT_LANG_MAP,
    to_tesseract_lang,
)
from payroll_copilot.infrastructure.ocr.preprocessing import (
    DocumentImagePreprocessor,
    OcrPreprocessingConfig,
)
from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("auto", "heb+eng"),
        ("he", "heb+eng"),
        ("en", "eng"),
        ("ar", "ara+eng"),
        ("HE", "heb+eng"),
        (" Auto ", "heb+eng"),
    ],
)
def test_to_tesseract_lang_mapping(requested: str, expected: str) -> None:
    assert to_tesseract_lang(requested) == expected


def test_auto_uses_default_multi_override() -> None:
    assert to_tesseract_lang("auto", default_multi="heb+eng+ara") == "heb+eng+ara"
    assert DEFAULT_TESSERACT_MULTI_LANG == "heb+eng"
    assert TESSERACT_LANG_MAP["auto"] == "heb+eng"


def test_unsupported_language_rejected() -> None:
    with pytest.raises(OcrLanguageNotSupportedError):
        normalize_document_language("fr")
    with pytest.raises(OcrLanguageNotSupportedError):
        to_tesseract_lang("fr")


def test_ui_locale_codes_still_normalize() -> None:
    """UI/assistant locales he|en|ar remain valid document-language inputs."""
    assert normalize_document_language("he") == "he"
    assert normalize_document_language("en") == "en"
    assert normalize_document_language("ar") == "ar"


@pytest.mark.asyncio
async def test_tesseract_provider_receives_resolved_lang_and_reports_effective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_image_to_data(image: Image.Image, **kwargs: object) -> dict[str, list[object]]:
        captured["lang"] = kwargs.get("lang")
        return {
            "text": ["ok"],
            "conf": ["88"],
            "left": [1],
            "top": [1],
            "width": [8],
            "height": [8],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "word_num": [1],
        }

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _fake_image_to_data,
    )

    provider = TesseractOCRProvider(
        default_multi_lang="heb+eng",
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
    )
    image = Image.new("RGB", (24, 16), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 20, 12), fill=(0, 0, 0))
    buffer = __import__("io").BytesIO()
    image.save(buffer, format="PNG")

    result = await provider.extract(
        content=buffer.getvalue(),
        media_type="image/png",
        filename="sample.png",
        language="auto",
    )

    assert captured["lang"] == "heb+eng"
    assert result.language_requested == "auto"
    assert result.language_effective == "heb+eng"
    assert result.engine == "tesseract"


@pytest.mark.asyncio
async def test_explicit_ar_resolves_to_ara_eng(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_image_to_data(image: Image.Image, **kwargs: object) -> dict[str, list[object]]:
        captured["lang"] = kwargs.get("lang")
        return {
            "text": ["ok"],
            "conf": ["90"],
            "left": [1],
            "top": [1],
            "width": [8],
            "height": [8],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "word_num": [1],
        }

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _fake_image_to_data,
    )

    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
    )
    image = Image.new("L", (16, 16), color=255)
    buffer = __import__("io").BytesIO()
    image.save(buffer, format="PNG")

    result = await provider.extract(
        content=buffer.getvalue(),
        media_type="image/png",
        filename="sample.png",
        language="ar",
    )

    assert captured["lang"] == "ara+eng"
    assert result.language_requested == "ar"
    assert result.language_effective == "ara+eng"
