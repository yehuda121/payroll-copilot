"""Safe PDF embedded-text extraction (no personal values logged)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import fitz

from payroll_copilot.application.exceptions import OcrCorruptedDocumentError, OcrEmptyDocumentError

logger = logging.getLogger(__name__)

# Legacy threshold kept for backward-compatible call sites/tests.
MIN_EMBEDDED_TEXT_CHARS = 40

_PRINTABLE_RE = re.compile(r"[\w\u0590-\u05FF\u0600-\u06FF]", re.UNICODE)
_REPLACEMENT_CHAR = "\ufffd"
_MEANINGFUL_LINE_MIN_CHARS = 3


@dataclass(frozen=True, slots=True)
class EmbeddedTextQuality:
    """Heuristic quality assessment for PDF embedded text layers."""

    usable: bool
    non_whitespace_chars: int
    printable_ratio: float
    meaningful_lines: int
    replacement_char_ratio: float
    pages_with_text: int
    page_count: int
    reason: str | None = None


def extract_embedded_pdf_text(pdf_bytes: bytes) -> tuple[list[str], int]:
    """Return (page_texts, page_count) using the PDF text layer only.

    Does not rasterize or OCR. Raises the same empty/corrupt errors as rasterization.
    """
    if not pdf_bytes:
        raise OcrEmptyDocumentError()

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise OcrCorruptedDocumentError("PDF could not be opened or is corrupted.") from exc

    try:
        if document.page_count == 0:
            raise OcrEmptyDocumentError("PDF has no pages.")
        pages: list[str] = []
        for index in range(document.page_count):
            page = document.load_page(index)
            pages.append(page.get_text("text") or "")
        return pages, document.page_count
    finally:
        document.close()


def assess_embedded_text_quality(page_texts: list[str]) -> EmbeddedTextQuality:
    """Decide whether embedded PDF text is usable without OCR."""
    page_count = len(page_texts)
    combined = "".join(page_texts)
    stripped = combined.strip()
    non_ws = sum(len((text or "").replace(" ", "").replace("\n", "").replace("\t", "")) for text in page_texts)

    if not stripped:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=0,
            printable_ratio=0.0,
            meaningful_lines=0,
            replacement_char_ratio=0.0,
            pages_with_text=0,
            page_count=page_count,
            reason="empty_text_layer",
        )

    printable = sum(1 for ch in stripped if ch.isprintable() or ch in "\n\t")
    printable_ratio = printable / max(len(stripped), 1)

    replacement_count = stripped.count(_REPLACEMENT_CHAR)
    replacement_char_ratio = replacement_count / max(len(stripped), 1)

    meaningful_lines = 0
    pages_with_text = 0
    for page_text in page_texts:
        page_stripped = (page_text or "").strip()
        if page_stripped:
            pages_with_text += 1
        for line in (page_text or "").splitlines():
            line_stripped = line.strip()
            if len(line_stripped) >= _MEANINGFUL_LINE_MIN_CHARS and _PRINTABLE_RE.search(line_stripped):
                meaningful_lines += 1

    # Short payslips may have few lines but still be valid text layers.
    min_chars = 20 if meaningful_lines >= 2 else 30

    if non_ws < min_chars:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=non_ws,
            printable_ratio=printable_ratio,
            meaningful_lines=meaningful_lines,
            replacement_char_ratio=replacement_char_ratio,
            pages_with_text=pages_with_text,
            page_count=page_count,
            reason="insufficient_text",
        )

    if printable_ratio < 0.80:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=non_ws,
            printable_ratio=printable_ratio,
            meaningful_lines=meaningful_lines,
            replacement_char_ratio=replacement_char_ratio,
            pages_with_text=pages_with_text,
            page_count=page_count,
            reason="low_printable_ratio",
        )

    if replacement_char_ratio > 0.08:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=non_ws,
            printable_ratio=printable_ratio,
            meaningful_lines=meaningful_lines,
            replacement_char_ratio=replacement_char_ratio,
            pages_with_text=pages_with_text,
            page_count=page_count,
            reason="garbled_replacement_chars",
        )

    if meaningful_lines < 1:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=non_ws,
            printable_ratio=printable_ratio,
            meaningful_lines=meaningful_lines,
            replacement_char_ratio=replacement_char_ratio,
            pages_with_text=pages_with_text,
            page_count=page_count,
            reason="no_meaningful_lines",
        )

    if page_count > 1 and pages_with_text == 0:
        return EmbeddedTextQuality(
            usable=False,
            non_whitespace_chars=non_ws,
            printable_ratio=printable_ratio,
            meaningful_lines=meaningful_lines,
            replacement_char_ratio=replacement_char_ratio,
            pages_with_text=pages_with_text,
            page_count=page_count,
            reason="no_page_text_distribution",
        )

    return EmbeddedTextQuality(
        usable=True,
        non_whitespace_chars=non_ws,
        printable_ratio=printable_ratio,
        meaningful_lines=meaningful_lines,
        replacement_char_ratio=replacement_char_ratio,
        pages_with_text=pages_with_text,
        page_count=page_count,
        reason=None,
    )


def embedded_text_is_usable(page_texts: list[str], *, min_chars: int = MIN_EMBEDDED_TEXT_CHARS) -> bool:
    """Backward-compatible usability check."""
    quality = assess_embedded_text_quality(page_texts)
    if quality.usable:
        return True
    # Preserve legacy threshold behavior for marginal cases.
    total = sum(len((text or "").strip()) for text in page_texts)
    return total >= min_chars and quality.reason not in {
        "garbled_replacement_chars",
        "low_printable_ratio",
        "empty_text_layer",
    }


def log_extraction_stage(
    *,
    stage: str,
    document_type: str,
    page_count: int | None = None,
    extracted_text_length: int | None = None,
    extracted_field_count: int | None = None,
    error_code: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """Structured diagnostics without personal values or raw OCR text."""
    logger.info(
        "extraction_diag stage=%s document_type=%s page_count=%s text_len=%s field_count=%s "
        "error_code=%s duration_ms=%s",
        stage,
        document_type,
        page_count if page_count is not None else "-",
        extracted_text_length if extracted_text_length is not None else "-",
        extracted_field_count if extracted_field_count is not None else "-",
        error_code or "-",
        f"{duration_ms:.1f}" if duration_ms is not None else "-",
    )
