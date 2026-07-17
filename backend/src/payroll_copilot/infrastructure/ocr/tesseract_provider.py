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
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage
from payroll_copilot.infrastructure.ocr.confidence import average_confidence
from payroll_copilot.infrastructure.ocr.language import (
    DEFAULT_TESSERACT_MULTI_LANG,
    normalize_document_language,
    to_tesseract_lang,
)
from payroll_copilot.infrastructure.ocr.media_types import is_pdf, resolve_media_type
from payroll_copilot.infrastructure.ocr.pdf_rasterizer import rasterize_pdf_to_png_pages
from payroll_copilot.infrastructure.ocr.pdf_text import (
    assess_embedded_text_quality,
    extract_embedded_pdf_text,
    log_extraction_stage,
)
from payroll_copilot.infrastructure.ocr.text_normalize import normalize_extracted_text
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
        started = time.perf_counter()
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
                page_texts, page_count = await asyncio.to_thread(extract_embedded_pdf_text, content)
                text_len = sum(len((t or "").strip()) for t in page_texts)
                log_extraction_stage(
                    stage="pdf_embedded_text",
                    document_type="payslip",
                    page_count=page_count,
                    extracted_text_length=text_len,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
                quality = assess_embedded_text_quality(page_texts)
                if quality.usable:
                    normalized_pages = [normalize_extracted_text(text) for text in page_texts]
                    pages = tuple(
                        OcrPage(
                            page=index,
                            language=tess_lang,
                            text=text.strip(),
                            confidence=None,
                            lines=tuple(
                                OcrLine(text=line, confidence=None, bbox=(0.0, 0.0, 0.0, 0.0), words=())
                                for line in text.splitlines()
                                if line.strip()
                            ),
                        )
                        for index, text in enumerate(normalized_pages, start=1)
                    )
                    raw_text = normalize_extracted_text(
                        "\n\n".join(page.text for page in pages if page.text)
                    )
                    log_extraction_stage(
                        stage="ocr_completed_embedded_text",
                        document_type="payslip",
                        page_count=page_count,
                        extracted_text_length=len(raw_text),
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                    return OCRResult(
                        pages=pages,
                        engine=f"{self.engine_name}+pdf_text",
                        language_requested=requested,
                        language_effective=tess_lang,
                        raw_text=raw_text,
                        overall_confidence=None,
                        fields=(),
                        warnings=("pdf_embedded_text_used",),
                    )

                page_images = await asyncio.to_thread(
                    rasterize_pdf_to_png_pages,
                    content,
                    max_pages=self._strategy.max_pages,
                )
                strategy_prefix = [f"pdf_embedded_text_insufficient:{quality.reason or 'unknown'}"]
            else:
                page_images = [content]
                strategy_prefix = []

            pages: list[OcrPage] = []
            page_confidences: list[float] = []
            strategy_warnings: list[str] = list(strategy_prefix)

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

            raw_text = normalize_extracted_text("\n\n".join(page.text for page in pages if page.text))
            log_extraction_stage(
                stage="ocr_completed",
                document_type="payslip",
                page_count=len(pages),
                extracted_text_length=len(raw_text),
                duration_ms=(time.perf_counter() - started) * 1000,
                error_code=None if raw_text else "ocr_empty_text",
            )
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
        if self._strategy.multi_psm_enabled:
            return self._strategy.psm_candidates[: self._strategy.max_candidates]
        return (self._strategy.primary_psm,)

    def _ocr_result_is_usable(self, layout: object, *, tess_lang: str) -> bool:
        text = getattr(layout, "text", "") or ""
        stripped = normalize_extracted_text(text)
        if len(stripped.replace(" ", "").replace("\n", "")) < self._strategy.min_usable_text_chars:
            return False
        valid_words = int(getattr(layout, "valid_word_count", 0) or 0)
        return valid_words > 0 or len(stripped) >= self._strategy.min_usable_text_chars

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

            psms_to_try = list(self._candidate_psms())
            if not self._strategy.multi_psm_enabled and self._strategy.fallback_psm not in psms_to_try:
                psms_to_try.append(self._strategy.fallback_psm)

            for psm in psms_to_try:
                if scored and not self._strategy.multi_psm_enabled:
                    # Adaptive mode: only try fallback when primary OCR is clearly unusable.
                    _, _, _, _, best_layout = scored[0]
                    if self._ocr_result_is_usable(best_layout, tess_lang=tess_lang):
                        break
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
                text=normalize_extracted_text(selected.text),
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
