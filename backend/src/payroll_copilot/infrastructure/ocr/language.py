"""Language mapping between API codes and OCR engine codes.

Re-exports application language normalization; engine-specific maps live here.

UI / assistant locales (he|en|ar) are independent of OCR engine language packs.
Israeli payslips default to Hebrew+English OCR; Arabic OCR is opt-in via ``ar``.
"""

from __future__ import annotations

from payroll_copilot.application.exceptions import OcrLanguageNotSupportedError
from payroll_copilot.application.ocr_input import normalize_document_language

# App document-language code → Tesseract ``-l`` string.
# ``auto`` / ``he`` intentionally omit Arabic to avoid script confusion on Hebrew payslips.
TESSERACT_LANG_MAP: dict[str, str] = {
    "he": "heb+eng",
    "en": "eng",
    "ar": "ara+eng",
    "auto": "heb+eng",
}

# App language → PaddleOCR lang argument.
# Note: PaddleOCR has no dedicated Hebrew recognizer model in official packs.
PADDLE_LANG_MAP: dict[str, str | None] = {
    "en": "en",
    "ar": "ar",
    "he": None,
    "auto": "en",
}

DEFAULT_TESSERACT_MULTI_LANG = "heb+eng"


def to_tesseract_lang(language: str, *, default_multi: str = DEFAULT_TESSERACT_MULTI_LANG) -> str:
    """Resolve an API document language to a Tesseract language pack string.

    ``auto`` uses ``default_multi`` (from settings ``TESSERACT_LANG``, default ``heb+eng``).
    Explicit ``he`` / ``en`` / ``ar`` use ``TESSERACT_LANG_MAP``.
    """
    normalized = normalize_document_language(language)
    if normalized == "auto":
        return default_multi or DEFAULT_TESSERACT_MULTI_LANG
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
    "DEFAULT_TESSERACT_MULTI_LANG",
    "normalize_document_language",
    "to_paddle_lang",
    "to_tesseract_lang",
    "PADDLE_LANG_MAP",
    "TESSERACT_LANG_MAP",
]
