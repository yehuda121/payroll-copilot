"""PDF rasterization shared by OCR providers (generic, no payroll logic)."""

from __future__ import annotations

import logging

import fitz

from payroll_copilot.application.exceptions import OcrCorruptedDocumentError, OcrEmptyDocumentError

logger = logging.getLogger(__name__)


def rasterize_pdf_to_png_pages(
    pdf_bytes: bytes,
    *,
    dpi: int = 200,
    max_pages: int | None = None,
) -> list[bytes]:
    """Render each PDF page to PNG bytes.

    Raises:
        OcrEmptyDocumentError: PDF has zero pages.
        OcrCorruptedDocumentError: PDF cannot be opened or rendered.
    """
    if not pdf_bytes:
        raise OcrEmptyDocumentError()

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — PyMuPDF raises varied errors for bad PDFs
        raise OcrCorruptedDocumentError("PDF could not be opened or is corrupted.") from exc

    try:
        if document.page_count == 0:
            raise OcrEmptyDocumentError("PDF has no pages.")

        pages: list[bytes] = []
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        limit = document.page_count if max_pages is None else min(document.page_count, max_pages)
        for index in range(limit):
            try:
                page = document.load_page(index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                pages.append(pixmap.tobytes("png"))
            except Exception as exc:  # noqa: BLE001
                raise OcrCorruptedDocumentError(
                    f"PDF page {index + 1} could not be rendered."
                ) from exc
        return pages
    finally:
        document.close()
