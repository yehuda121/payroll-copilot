"""Application-level OCR input helpers (generic — no infrastructure deps)."""

from __future__ import annotations

from pathlib import Path

from payroll_copilot.application.exceptions import (
    OcrLanguageNotSupportedError,
    OcrUnsupportedFileError,
)

ALLOWED_DOCUMENT_LANGUAGES = frozenset({"he", "en", "ar", "auto"})

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
SUPPORTED_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
    }
)

_EXTENSION_MEDIA: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def normalize_document_language(language: str) -> str:
    normalized = (language or "auto").strip().lower()
    if normalized not in ALLOWED_DOCUMENT_LANGUAGES:
        raise OcrLanguageNotSupportedError(
            f"Unsupported language '{language}'. Allowed: he, en, ar, auto."
        )
    return normalized


def resolve_media_type(*, filename: str | None, content_type: str | None) -> str:
    hinted = (content_type or "").split(";")[0].strip().lower()
    if hinted in SUPPORTED_MEDIA_TYPES:
        return "image/jpeg" if hinted == "image/jpg" else hinted

    suffix = Path(filename or "").suffix.lower()
    if suffix in _EXTENSION_MEDIA:
        return _EXTENSION_MEDIA[suffix]

    raise OcrUnsupportedFileError(
        "Unsupported file type. Allowed: PDF, PNG, JPG, JPEG."
    )


def is_pdf(media_type: str) -> bool:
    return media_type == "application/pdf"
