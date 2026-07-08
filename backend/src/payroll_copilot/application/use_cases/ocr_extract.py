"""OCR text extraction use case — generic document layer only.

Pipeline ownership:
  Document → OCR (this use case) → AI Parser (future) → Structured Payroll Data
  → Validation Engine → AI Explanation

This layer never parses payroll fields and is never consumed directly by the
deterministic Validation Engine.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from payroll_copilot.application.exceptions import (
    OcrEmptyDocumentError,
    OcrTimeoutError,
)
from payroll_copilot.application.ocr_input import (
    normalize_document_language,
    resolve_media_type,
)
from payroll_copilot.application.ports.ocr import OCRProvider, OCRResult


@dataclass(frozen=True, slots=True)
class ExtractDocumentTextCommand:
    content: bytes
    filename: str | None
    content_type: str | None
    language: str = "auto"


class ExtractDocumentTextUseCase:
    """Run pluggable OCR and return structured page-level text + confidence."""

    def __init__(self, ocr_provider: OCRProvider, *, timeout_seconds: float) -> None:
        self._ocr_provider = ocr_provider
        self._timeout_seconds = timeout_seconds

    async def execute(self, command: ExtractDocumentTextCommand) -> OCRResult:
        if not command.content:
            raise OcrEmptyDocumentError()

        language = normalize_document_language(command.language)
        media_type = resolve_media_type(
            filename=command.filename,
            content_type=command.content_type,
        )

        try:
            return await asyncio.wait_for(
                self._ocr_provider.extract(
                    content=command.content,
                    media_type=media_type,
                    filename=command.filename,
                    language=language,
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise OcrTimeoutError(
                f"OCR processing timed out after {self._timeout_seconds:.0f}s."
            ) from exc
