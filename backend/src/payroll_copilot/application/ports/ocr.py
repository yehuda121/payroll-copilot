"""OCR port: generic document text extraction (no payroll domain logic).

Future pipeline (owned by other layers — not OCR):
  Document → OCR → AI Parser → Structured Payroll Data → Validation Engine → AI Explanation

The Validation Engine must never consume OCR output directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OcrWord:
    """A single OCR word with geometry in processed-image coordinates.

    ``bbox`` is ``(x, y, width, height)`` with origin at the top-left of the
    preprocessed image passed to Tesseract.
    """

    text: str
    confidence: float | None
    bbox: tuple[float, float, float, float]
    block_number: int = 0
    paragraph_number: int = 0
    line_number: int = 0
    word_number: int = 0


@dataclass(frozen=True, slots=True)
class OcrLine:
    """A single line (or text unit) returned by the OCR engine."""

    text: str
    confidence: float | None
    bbox: tuple[float, float, float, float] | None = None
    words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrPage:
    """OCR result for one page / image."""

    page: int
    language: str
    text: str
    confidence: float | None
    lines: tuple[OcrLine, ...] = ()
    words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True, slots=True)
class OCRResult:
    """Structured OCR extraction result.

    Generic document text only — no field names, payslip semantics, or payroll parsing.
    ``fields`` remains empty in Phase 1 (field extraction belongs to a future AI Parser).
    """

    pages: tuple[OcrPage, ...]
    engine: str
    language_requested: str
    language_effective: str
    raw_text: str
    overall_confidence: float | None
    fields: tuple[object, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def page_count(self) -> int:
        return len(self.pages)


@runtime_checkable
class OCRProvider(Protocol):
    """Pluggable OCR engine port.

    Implementations extract text and OCR metadata from images/PDFs.
    They must not contain payroll-specific logic.
    """

    @property
    def engine_name(self) -> str: ...

    async def extract(
        self,
        *,
        content: bytes,
        media_type: str,
        filename: str | None = None,
        language: str = "auto",
    ) -> OCRResult:
        """Extract text from a PDF or image document.

        ``language`` uses application codes: ``he`` | ``en`` | ``ar`` | ``auto``.
        Providers map these to engine-specific codes internally.
        """
        ...
