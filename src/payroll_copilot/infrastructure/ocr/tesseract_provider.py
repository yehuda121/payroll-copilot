"""Tesseract OCR provider implementation."""

from __future__ import annotations

import io

import fitz
from PIL import Image
import pytesseract

from payroll_copilot.application.ports import OCRField, OCRResult


class TesseractOCRProvider:
    """OCR extraction using Tesseract."""

    def __init__(self, default_languages: str = "heb+eng+ara") -> None:
        self._default_languages = default_languages

    async def extract_text(
        self, image_bytes: bytes, *, languages: str | None = None
    ) -> OCRResult:
        lang = languages or self._default_languages
        image = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)

        text_parts: list[str] = []
        confidences: list[float] = []
        fields: list[OCRField] = []

        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            conf = float(data["conf"][i])
            if conf >= 0:
                text_parts.append(word)
                confidences.append(conf / 100.0)

        raw_text = " ".join(text_parts)
        overall = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            raw_text=raw_text,
            fields=fields,
            overall_confidence=overall,
            engine="tesseract",
        )

    async def extract_from_pdf(
        self, pdf_bytes: bytes, *, languages: str | None = None
    ) -> OCRResult:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text: list[str] = []
        all_confidences: list[float] = []

        for page in doc:
            pix = page.get_pixmap(dpi=300)
            image_bytes = pix.tobytes("png")
            page_result = await self.extract_text(image_bytes, languages=languages)
            all_text.append(page_result.raw_text)
            if page_result.overall_confidence > 0:
                all_confidences.append(page_result.overall_confidence)

        doc.close()
        overall = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        return OCRResult(
            raw_text="\n\n".join(all_text),
            fields=[],
            overall_confidence=overall,
            engine="tesseract",
        )


def create_ocr_provider(provider_name: str, settings: object) -> TesseractOCRProvider:
    if provider_name == "tesseract":
        return TesseractOCRProvider(
            default_languages=getattr(settings, "tesseract_lang", "heb+eng+ara")
        )
    msg = f"Unsupported OCR provider: {provider_name}"
    raise ValueError(msg)
