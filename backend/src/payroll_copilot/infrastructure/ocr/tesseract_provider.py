"""Tesseract OCR provider — generic document text extraction only."""

from __future__ import annotations

import asyncio
import io
import logging

from PIL import Image
import pytesseract

from payroll_copilot.application.exceptions import (
    OcrEmptyDocumentError,
    OcrProviderError,
)
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage
from payroll_copilot.infrastructure.ocr.confidence import average_confidence
from payroll_copilot.infrastructure.ocr.language import (
    normalize_document_language,
    to_tesseract_lang,
)
from payroll_copilot.infrastructure.ocr.media_types import is_pdf, resolve_media_type
from payroll_copilot.infrastructure.ocr.pdf_rasterizer import rasterize_pdf_to_png_pages

logger = logging.getLogger(__name__)


class TesseractOCRProvider:
    """OCR extraction using Tesseract (pluggable OCRProvider implementation)."""

    def __init__(self, *, default_multi_lang: str = "heb+eng+ara") -> None:
        self._default_multi_lang = default_multi_lang

    @property
    def engine_name(self) -> str:
        return "tesseract"

    async def extract(
        self,
        *,
        content: bytes,
        media_type: str,
        filename: str | None = None,
        language: str = "auto",
    ) -> OCRResult:
        if not content:
            raise OcrEmptyDocumentError()

        resolved_media = resolve_media_type(filename=filename, content_type=media_type)
        requested = normalize_document_language(language)
        tess_lang = to_tesseract_lang(requested, default_multi=self._default_multi_lang)

        try:
            if is_pdf(resolved_media):
                page_images = await asyncio.to_thread(rasterize_pdf_to_png_pages, content)
            else:
                page_images = [content]

            pages: list[OcrPage] = []
            page_confidences: list[float] = []

            for index, image_bytes in enumerate(page_images, start=1):
                page = await asyncio.to_thread(
                    self._extract_image_sync,
                    image_bytes,
                    page_number=index,
                    language_label=requested,
                    tess_lang=tess_lang,
                )
                pages.append(page)
                if page.confidence is not None:
                    page_confidences.append(page.confidence)

            if not pages:
                raise OcrEmptyDocumentError()

            raw_text = "\n\n".join(page.text for page in pages if page.text).strip()
            return OCRResult(
                pages=tuple(pages),
                engine=self.engine_name,
                language_requested=requested,
                language_effective=requested,
                raw_text=raw_text,
                overall_confidence=average_confidence(page_confidences),
                fields=(),
                warnings=(),
            )
        except (OcrEmptyDocumentError, OcrProviderError):
            raise
        except Exception as exc:  # noqa: BLE001 — surface engine failures uniformly
            logger.exception("Tesseract OCR failed")
            raise OcrProviderError(f"Tesseract OCR failed: {exc}") from exc

    def _extract_image_sync(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
        language_label: str,
        tess_lang: str,
    ) -> OcrPage:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(f"Image could not be opened for OCR: {exc}") from exc

        try:
            data = pytesseract.image_to_data(
                image,
                lang=tess_lang,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(f"Tesseract engine error: {exc}") from exc

        lines_map: dict[tuple[int, int], list[tuple[str, float]]] = {}
        confidences: list[float] = []

        n = len(data.get("text", []))
        for i in range(n):
            word = (data["text"][i] or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError, KeyError):
                continue
            if conf < 0:
                continue
            conf_norm = conf / 100.0
            confidences.append(conf_norm)
            key = (int(data.get("block_num", [0])[i]), int(data.get("line_num", [0])[i]))
            lines_map.setdefault(key, []).append((word, conf_norm))

        ocr_lines: list[OcrLine] = []
        text_parts: list[str] = []
        for _key, words in lines_map.items():
            line_text = " ".join(w for w, _ in words).strip()
            if not line_text:
                continue
            line_conf = average_confidence([c for _, c in words])
            ocr_lines.append(OcrLine(text=line_text, confidence=line_conf, bbox=None))
            text_parts.append(line_text)

        page_text = "\n".join(text_parts).strip()
        return OcrPage(
            page=page_number,
            language=language_label,
            text=page_text,
            confidence=average_confidence(confidences),
            lines=tuple(ocr_lines),
        )
