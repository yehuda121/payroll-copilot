"""Shared deterministic PDF text extraction (PyMuPDF text layer only — no OCR/AI)."""

from __future__ import annotations

from dataclasses import dataclass

import fitz

from payroll_copilot.application.exceptions import OcrCorruptedDocumentError, OcrEmptyDocumentError
from payroll_copilot.application.services.deterministic_pdf.types import (
    DeterministicExtractionErrorCode,
)
from payroll_copilot.application.services.text_normalize import normalize_extracted_text
from payroll_copilot.infrastructure.ocr.pdf_text import (
    assess_embedded_text_quality,
    extract_embedded_pdf_text,
)


@dataclass(frozen=True, slots=True)
class PdfTextLayerResult:
    """Outcome of reading a PDF's embedded text layer."""

    ok: bool
    page_texts: tuple[str, ...]
    page_count: int
    raw_text: str
    error_code: str | None = None
    error_message: str | None = None
    quality_reason: str | None = None


_PDF_MAGIC = b"%PDF"


def is_pdf_bytes(content: bytes, *, filename: str | None = None, mime_type: str | None = None) -> bool:
    if content.startswith(_PDF_MAGIC):
        return True
    name = (filename or "").lower()
    mime = (mime_type or "").lower().strip()
    if mime == "application/pdf" and content[:4] == b"%PDF":
        return True
    if name.endswith(".pdf") and content.startswith(_PDF_MAGIC):
        return True
    return False


def extract_pdf_text_layer(
    content: bytes,
    *,
    filename: str | None = None,
    mime_type: str | None = None,
) -> PdfTextLayerResult:
    """Single source of truth: PDF bytes → page texts (deterministic, no OCR/AI).

    Returns a typed result for empty / encrypted / malformed / OCR-required cases
    instead of raising, so callers can surface clear codes.
    """
    if not content:
        return PdfTextLayerResult(
            ok=False,
            page_texts=(),
            page_count=0,
            raw_text="",
            error_code=DeterministicExtractionErrorCode.EMPTY_PDF.value,
            error_message="PDF file is empty.",
        )

    if not is_pdf_bytes(content, filename=filename, mime_type=mime_type):
        return PdfTextLayerResult(
            ok=False,
            page_texts=(),
            page_count=0,
            raw_text="",
            error_code=DeterministicExtractionErrorCode.NOT_PDF.value,
            error_message="Only PDF files are supported for deterministic extraction.",
        )

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception:  # noqa: BLE001
        return PdfTextLayerResult(
            ok=False,
            page_texts=(),
            page_count=0,
            raw_text="",
            error_code=DeterministicExtractionErrorCode.MALFORMED_PDF.value,
            error_message="PDF could not be opened or is corrupted.",
        )

    try:
        if document.is_encrypted:
            # Empty password may unlock some "owner-password only" files.
            authenticated = False
            try:
                authenticated = bool(document.authenticate(""))
            except Exception:  # noqa: BLE001
                authenticated = False
            if not authenticated:
                return PdfTextLayerResult(
                    ok=False,
                    page_texts=(),
                    page_count=document.page_count,
                    raw_text="",
                    error_code=DeterministicExtractionErrorCode.ENCRYPTED_PDF.value,
                    error_message="Password-protected PDF files are not supported.",
                )
        if document.page_count == 0:
            return PdfTextLayerResult(
                ok=False,
                page_texts=(),
                page_count=0,
                raw_text="",
                error_code=DeterministicExtractionErrorCode.EMPTY_PDF.value,
                error_message="PDF has no pages.",
            )
    finally:
        document.close()

    try:
        pages, page_count = extract_embedded_pdf_text(content)
    except OcrEmptyDocumentError as exc:
        return PdfTextLayerResult(
            ok=False,
            page_texts=(),
            page_count=0,
            raw_text="",
            error_code=DeterministicExtractionErrorCode.EMPTY_PDF.value,
            error_message=str(exc) or "PDF has no pages.",
        )
    except OcrCorruptedDocumentError as exc:
        return PdfTextLayerResult(
            ok=False,
            page_texts=(),
            page_count=0,
            raw_text="",
            error_code=DeterministicExtractionErrorCode.MALFORMED_PDF.value,
            error_message=str(exc) or "PDF could not be opened or is corrupted.",
        )

    quality = assess_embedded_text_quality(pages)
    normalized_pages = tuple(normalize_extracted_text(page or "") for page in pages)
    raw_text = normalize_extracted_text("\n".join(normalized_pages))

    if not quality.usable:
        return PdfTextLayerResult(
            ok=False,
            page_texts=normalized_pages,
            page_count=page_count,
            raw_text=raw_text,
            error_code=DeterministicExtractionErrorCode.OCR_REQUIRED.value,
            error_message=(
                "This PDF has no usable text layer. OCR is required for scanned or image-only PDFs."
            ),
            quality_reason=quality.reason,
        )

    return PdfTextLayerResult(
        ok=True,
        page_texts=normalized_pages,
        page_count=page_count,
        raw_text=raw_text,
        quality_reason=quality.reason,
    )
