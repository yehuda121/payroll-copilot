"""Language mapping between API codes and OCR engine codes.

Re-exports application language normalization; engine-specific maps live here.
"""

from __future__ import annotations

from payroll_copilot.application.exceptions import OcrLanguageNotSupportedError
from payroll_copilot.application.ocr_input import normalize_document_language

# App language → Tesseract lang string
TESSERACT_LANG_MAP: dict[str, str] = {
    "he": "heb",
    "en": "eng",
    "ar": "ara",
    "auto": "heb+eng+ara",
}

# App language → PaddleOCR lang argument.
# Note: PaddleOCR has no dedicated Hebrew recognizer model in official packs.
PADDLE_LANG_MAP: dict[str, str | None] = {
    "en": "en",
    "ar": "ar",
    "he": None,
    "auto": "en",
}


def to_tesseract_lang(language: str, *, default_multi: str = "heb+eng+ara") -> str:
    normalized = normalize_document_language(language)
    if normalized == "auto":
        return default_multi
    return TESSERACT_LANG_MAP[normalized]


def to_paddle_lang(language: str) -> str:
    """Map to a PaddleOCR language code.

    Raises OcrLanguageNotSupportedError when the engine has no model for that language.
    """
    normalized = normalize_document_language(language)
    paddle_lang = PADDLE_LANG_MAP[normalized]
    if paddle_lang is None:
        raise OcrLanguageNotSupportedError(
            "Hebrew is not available in the PaddleOCR provider. "
            "Hebrew documents are routed to Tesseract by the default factory (H1)."
        )
    return paddle_lang


__all__ = [
    "normalize_document_language",
    "to_paddle_lang",
    "to_tesseract_lang",
    "PADDLE_LANG_MAP",
    "TESSERACT_LANG_MAP",
]
