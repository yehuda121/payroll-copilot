"""Tesseract OCR provider — layout-aware multi-PSM extraction."""

from __future__ import annotations

import asyncio
import io
import logging
import time

from PIL import Image
from PIL.Image import DecompressionBombError
import pytesseract

from payroll_copilot.application.exceptions import (
    OcrCorruptedDocumentError,
    OcrEmptyDocumentError,
    OcrProviderError,
)
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.infrastructure.ocr.confidence import average_confidence
from payroll_copilot.infrastructure.ocr.language import (
    DEFAULT_TESSERACT_MULTI_LANG,
    normalize_document_language,
    to_tesseract_lang,
)
from payroll_copilot.infrastructure.ocr.media_types import is_pdf, resolve_media_type
from payroll_copilot.infrastructure.ocr.pdf_rasterizer import rasterize_pdf_to_png_pages
from payroll_copilot.infrastructure.ocr.preprocessing import (
    DocumentImagePreprocessor,
    OcrPreprocessingConfig,
)
from payroll_copilot.infrastructure.ocr.tesseract_config import (
    TesseractStrategyConfig,
    build_tesseract_config,
)
from payroll_copilot.infrastructure.ocr.tesseract_layout import build_layout_candidate
from payroll_copilot.infrastructure.ocr.tesseract_scoring import (
    score_layout_candidate,
    select_best_candidate,
)

logger = logging.getLogger(__name__)


class TesseractOCRProvider:
    """OCR extraction using Tesseract with deterministic multi-PSM selection."""

    def __init__(
        self,
        *,
        default_multi_lang: str = DEFAULT_TESSERACT_MULTI_LANG,
        preprocessor: DocumentImagePreprocessor | None = None,
        strategy: TesseractStrategyConfig | None = None,
    ) -> None:
        self._default_multi_lang = default_multi_lang
        self._preprocessor = preprocessor or DocumentImagePreprocessor(OcrPreprocessingConfig())
        self._strategy = strategy or TesseractStrategyConfig()

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
        logger.debug(
            "ocr_language_resolved engine=%s language_requested=%s tesseract_lang=%s",
            self.engine_name,
            requested,
            tess_lang,
        )

        try:
            if is_pdf(resolved_media):
                page_images = await asyncio.to_thread(rasterize_pdf_to_png_pages, content)
            else:
                page_images = [content]

            pages: list[OcrPage] = []
            page_confidences: list[float] = []
            strategy_warnings: list[str] = []

            for index, image_bytes in enumerate(page_images, start=1):
                page, warning = await asyncio.to_thread(
                    self._extract_image_sync,
                    image_bytes,
                    page_number=index,
                    language_label=requested,
                    tess_lang=tess_lang,
                )
                pages.append(page)
                if page.confidence is not None:
                    page_confidences.append(page.confidence)
                if warning:
                    strategy_warnings.append(warning)

            if not pages:
                raise OcrEmptyDocumentError()

            raw_text = "\n\n".join(page.text for page in pages if page.text).strip()
            return OCRResult(
                pages=tuple(pages),
                engine=self.engine_name,
                language_requested=requested,
                language_effective=tess_lang,
                raw_text=raw_text,
                overall_confidence=average_confidence(page_confidences),
                fields=(),
                warnings=tuple(dict.fromkeys(strategy_warnings)),
            )
        except (OcrEmptyDocumentError, OcrProviderError, OcrCorruptedDocumentError):
            raise
        except Exception as exc:  # noqa: BLE001 — surface engine failures uniformly
            logger.exception("Tesseract OCR failed")
            raise OcrProviderError(f"Tesseract OCR failed: {exc}") from exc

    def _candidate_psms(self) -> tuple[int, ...]:
        if not self._strategy.multi_psm_enabled:
            return (self._strategy.psm_candidates[0],)
        return self._strategy.psm_candidates[: self._strategy.max_candidates]

    def _extract_image_sync(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
        language_label: str,
        tess_lang: str,
    ) -> tuple[OcrPage, str | None]:
        page_started = time.perf_counter()
        try:
            source = Image.open(io.BytesIO(image_bytes))
            source.load()
        except DecompressionBombError as exc:
            raise OcrProviderError(
                "Image exceeds safe pixel limits and cannot be opened for OCR."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise OcrCorruptedDocumentError(f"Image could not be opened for OCR: {exc}") from exc

        ocr_image: Image.Image | None = None
        try:
            processed = self._preprocessor.process(source)
            ocr_image = processed.image
            width, height = ocr_image.size
            logger.debug(
                "ocr_page_preprocess page=%s enabled=%s processed_size=%sx%s original_size=%sx%s scale=%.4f",
                page_number,
                processed.enabled,
                processed.processed_size[0],
                processed.processed_size[1],
                processed.original_size[0],
                processed.original_size[1],
                processed.scale_factor,
            )

            oem = self._strategy.default_oem
            scored: list[tuple[int, float, float, int, object]] = []
            failures = 0

            for psm in self._candidate_psms():
                candidate_started = time.perf_counter()
                config = build_tesseract_config(oem=oem, psm=psm)
                try:
                    data = pytesseract.image_to_data(
                        ocr_image,
                        lang=tess_lang,
                        config=config,
                        output_type=pytesseract.Output.DICT,
                    )
                    layout = build_layout_candidate(
                        data,
                        min_confidence=self._strategy.min_valid_word_confidence,
                    )
                    quality = score_layout_candidate(
                        layout,
                        tess_lang=tess_lang,
                        image_width=width,
                        image_height=height,
                    )
                    mean_conf = float(layout.mean_confidence or 0.0)
                    scored.append((psm, quality, mean_conf, layout.valid_word_count, layout))
                    logger.debug(
                        "ocr_candidate engine=%s language_requested=%s tesseract_lang=%s "
                        "processed_size=%sx%s psm=%s oem=%s valid_words=%s mean_confidence=%.4f "
                        "quality_score=%.4f duration_ms=%.2f",
                        self.engine_name,
                        language_label,
                        tess_lang,
                        width,
                        height,
                        psm,
                        oem,
                        layout.valid_word_count,
                        mean_conf,
                        quality,
                        (time.perf_counter() - candidate_started) * 1000.0,
                    )
                except Exception as exc:  # noqa: BLE001 — isolate candidate failures
                    failures += 1
                    logger.debug(
                        "ocr_candidate_failed engine=%s psm=%s oem=%s error_type=%s duration_ms=%.2f",
                        self.engine_name,
                        psm,
                        oem,
                        type(exc).__name__,
                        (time.perf_counter() - candidate_started) * 1000.0,
                    )

            if not scored:
                raise OcrProviderError(
                    "Tesseract OCR failed for all configured page-segmentation candidates."
                )

            selected_psm, selected_score, selected = select_best_candidate(scored)  # type: ignore[arg-type]
            warning = (
                f"tesseract_strategy selected_psm={selected_psm} selected_oem={oem} "
                f"quality_score={selected_score:.4f} candidates={len(scored)} "
                f"processed_size={width}x{height}"
            )
            logger.debug(
                "ocr_candidate_selected engine=%s tesseract_lang=%s selected_psm=%s selected_oem=%s "
                "selected_score=%.4f candidates=%s failures=%s page_duration_ms=%.2f",
                self.engine_name,
                tess_lang,
                selected_psm,
                oem,
                selected_score,
                len(scored),
                failures,
                (time.perf_counter() - page_started) * 1000.0,
            )

            page = OcrPage(
                page=page_number,
                language=language_label,
                text=selected.text,
                confidence=selected.mean_confidence,
                lines=selected.lines,
                words=selected.words,
            )
            return page, warning
        except (OcrProviderError, OcrCorruptedDocumentError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrProviderError(f"Tesseract engine error: {exc}") from exc
        finally:
            source.close()
            if ocr_image is not None and ocr_image is not source:
                ocr_image.close()
