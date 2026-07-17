"""PaddleOCR provider — generic document text extraction only.

Hebrew is not supported by official PaddleOCR recognizers; callers must not
invent Hebrew Paddle support. Routing for Hebrew is handled by the factory /
routing provider (H1 fallback to Tesseract).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from payroll_copilot.application.exceptions import (
    OcrEmptyDocumentError,
    OcrLanguageNotSupportedError,
    OcrProviderError,
    OcrProviderUnavailableError,
)
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage
from payroll_copilot.infrastructure.ocr.confidence import (
    average_confidence,
    normalize_paddle_score,
)
from payroll_copilot.infrastructure.ocr.language import (
    normalize_document_language,
    to_paddle_lang,
)
from payroll_copilot.infrastructure.ocr.media_types import is_pdf, resolve_media_type
from payroll_copilot.infrastructure.ocr.pdf_rasterizer import rasterize_pdf_to_png_pages
from payroll_copilot.infrastructure.ocr.pdf_text import (
    assess_embedded_text_quality,
    extract_embedded_pdf_text,
    log_extraction_stage,
)

logger = logging.getLogger(__name__)


class PaddleOCRProvider:
    """OCR extraction using PaddleOCR (pluggable OCRProvider implementation)."""

    def __init__(self, *, use_gpu: bool = False) -> None:
        self._use_gpu = use_gpu
        self._engines: dict[str, Any] = {}

    @property
    def engine_name(self) -> str:
        return "paddleocr"

    def _get_engine(self, paddle_lang: str) -> Any:
        if paddle_lang in self._engines:
            return self._engines[paddle_lang]
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except ImportError as exc:
            raise OcrProviderUnavailableError(
                "PaddleOCR is not installed. Install optional extra: "
                "pip install 'payroll-copilot[ocr-paddle]' "
                "(or paddlepaddle + paddleocr)."
            ) from exc

        try:
            engine = PaddleOCR(
                use_angle_cls=True,
                lang=paddle_lang,
                use_gpu=self._use_gpu,
                show_log=False,
            )
        except TypeError:
            # Newer PaddleOCR versions renamed/removed some kwargs.
            engine = PaddleOCR(lang=paddle_lang)
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(f"Failed to initialize PaddleOCR: {exc}") from exc

        self._engines[paddle_lang] = engine
        return engine

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
        paddle_lang = to_paddle_lang(requested)
        warnings: list[str] = []

        try:
            if is_pdf(resolved_media):
                page_texts, page_count = await asyncio.to_thread(extract_embedded_pdf_text, content)
                text_len = sum(len((t or "").strip()) for t in page_texts)
                log_extraction_stage(
                    stage="pdf_embedded_text",
                    document_type="payslip",
                    page_count=page_count,
                    extracted_text_length=text_len,
                )
                if assess_embedded_text_quality(page_texts).usable:
                    pages = tuple(
                        OcrPage(
                            page=index,
                            language=requested,
                            text=text.strip(),
                            confidence=None,
                            lines=tuple(
                                OcrLine(text=line, confidence=None, bbox=(0.0, 0.0, 0.0, 0.0), words=())
                                for line in text.splitlines()
                                if line.strip()
                            ),
                        )
                        for index, text in enumerate(page_texts, start=1)
                    )
                    raw_text = "\n\n".join(page.text for page in pages if page.text).strip()
                    return OCRResult(
                        pages=pages,
                        engine=f"{self.engine_name}+pdf_text",
                        language_requested=requested,
                        language_effective=requested,
                        raw_text=raw_text,
                        overall_confidence=None,
                        fields=(),
                        warnings=("pdf_embedded_text_used",),
                    )
                page_images = await asyncio.to_thread(rasterize_pdf_to_png_pages, content)
                warnings.append("pdf_embedded_text_insufficient_ocr_fallback")
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
                    paddle_lang=paddle_lang,
                )
                pages.append(page)
                if page.confidence is not None:
                    page_confidences.append(page.confidence)

            if not pages:
                raise OcrEmptyDocumentError()

            raw_text = "\n\n".join(page.text for page in pages if page.text).strip()
            log_extraction_stage(
                stage="ocr_completed",
                document_type="payslip",
                page_count=len(pages),
                extracted_text_length=len(raw_text),
                error_code=None if raw_text else "ocr_empty_text",
            )
            return OCRResult(
                pages=tuple(pages),
                engine=self.engine_name,
                language_requested=requested,
                language_effective=requested,
                raw_text=raw_text,
                overall_confidence=average_confidence(page_confidences),
                fields=(),
                warnings=tuple(dict.fromkeys(warnings)),
            )
        except (
            OcrEmptyDocumentError,
            OcrLanguageNotSupportedError,
            OcrProviderError,
            OcrProviderUnavailableError,
        ):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("PaddleOCR failed")
            raise OcrProviderError(f"PaddleOCR failed: {exc}") from exc

    def _extract_image_sync(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
        language_label: str,
        paddle_lang: str,
    ) -> OcrPage:
        engine = self._get_engine(paddle_lang)
        # PaddleOCR APIs commonly expect a filesystem path.
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            raw = engine.ocr(tmp_path, cls=True)
        except TypeError:
            raw = engine.ocr(tmp_path)
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(f"PaddleOCR engine error: {exc}") from exc
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        lines, confidences = _parse_paddle_result(raw)
        page_text = "\n".join(line.text for line in lines).strip()
        return OcrPage(
            page=page_number,
            language=language_label,
            text=page_text,
            confidence=average_confidence(confidences),
            lines=tuple(lines),
        )


def _parse_paddle_result(raw: Any) -> tuple[list[OcrLine], list[float]]:
    """Parse PaddleOCR result formats into lines + real confidences."""
    lines: list[OcrLine] = []
    confidences: list[float] = []

    if raw is None:
        return lines, confidences

    # Classic format: list[list[[bbox], (text, score)]] (sometimes wrapped one more level)
    pages = raw
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        pages = raw

    for page in pages if isinstance(pages, list) else []:
        if page is None:
            continue
        if not isinstance(page, list):
            continue
        for item in page:
            text, score, bbox = _unpack_line_item(item)
            if not text:
                continue
            conf = normalize_paddle_score(score)
            if conf is not None:
                confidences.append(conf)
            lines.append(OcrLine(text=text, confidence=conf, bbox=bbox))

    return lines, confidences


def _unpack_line_item(
    item: Any,
) -> tuple[str, object | None, tuple[float, float, float, float] | None]:
    if item is None:
        return "", None, None

    # Typical: [bbox, (text, conf)]
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        bbox_raw = item[0]
        payload = item[1]
        text = ""
        score: object | None = None
        if isinstance(payload, (list, tuple)) and len(payload) >= 1:
            text = str(payload[0]).strip()
            score = payload[1] if len(payload) > 1 else None
        elif isinstance(payload, str):
            text = payload.strip()
        return text, score, _bbox_from_points(bbox_raw)

    return "", None, None


def _bbox_from_points(points: Any) -> tuple[float, float, float, float] | None:
    try:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:  # noqa: BLE001
        return None
