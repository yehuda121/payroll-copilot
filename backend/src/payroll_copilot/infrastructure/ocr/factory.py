"""OCR provider factory and Hebrew-aware routing (H1).

Primary engine: PaddleOCR (en/ar/auto).
Hebrew (`he`): intentional production fallback to Tesseract — not a bug.
OCR remains generic; no payroll-specific logic.
"""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.ocr_input import normalize_document_language
from payroll_copilot.application.ports.ocr import OCRProvider, OCRResult

logger = logging.getLogger(__name__)

HEBREW_FALLBACK_WARNING = (
    "Hebrew documents use Tesseract fallback because PaddleOCR has no official "
    "production-ready Hebrew recognizer. This is intentional."
)


class RoutingOCRProvider:
    """Routes requests to PaddleOCR or Tesseract based on language (H1).

    Exposes the actual engine used on the OCRResult — fallback is never hidden.
    """

    def __init__(
        self,
        *,
        primary: OCRProvider,
        hebrew_fallback: OCRProvider,
        primary_name: str = "paddleocr",
    ) -> None:
        self._primary = primary
        self._hebrew_fallback = hebrew_fallback
        self._primary_name = primary_name

    @property
    def engine_name(self) -> str:
        return self._primary_name

    async def extract(
        self,
        *,
        content: bytes,
        media_type: str,
        filename: str | None = None,
        language: str = "auto",
    ) -> OCRResult:
        requested = normalize_document_language(language)

        if requested == "he":
            result = await self._hebrew_fallback.extract(
                content=content,
                media_type=media_type,
                filename=filename,
                language=requested,
            )
            warnings = tuple(dict.fromkeys([*result.warnings, HEBREW_FALLBACK_WARNING]))
            return OCRResult(
                pages=result.pages,
                engine=result.engine,
                language_requested=requested,
                language_effective=result.language_effective,
                raw_text=result.raw_text,
                overall_confidence=result.overall_confidence,
                fields=(),
                warnings=warnings,
            )

        return await self._primary.extract(
            content=content,
            media_type=media_type,
            filename=filename,
            language=requested,
        )


def create_ocr_provider(provider_name: str, settings: Any) -> OCRProvider:
    """Create the configured OCR provider.

    Defaults to PaddleOCR with Hebrew → Tesseract routing when provider is paddleocr.
    Provider modules are imported lazily.
    """
    name = (provider_name or "paddleocr").strip().lower()

    from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider

    tesseract = TesseractOCRProvider(
        default_multi_lang=getattr(settings, "tesseract_lang", "heb+eng+ara")
    )
    use_gpu = bool(getattr(settings, "ocr_use_gpu", False))

    if name in {"paddle", "paddleocr"}:
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            logger.warning(
                "PaddleOCR package not installed; using Tesseract for all languages. "
                "Install with: pip install 'payroll-copilot[ocr-paddle]'."
            )
            return tesseract

        from payroll_copilot.infrastructure.ocr.paddleocr_provider import PaddleOCRProvider

        paddle = PaddleOCRProvider(use_gpu=use_gpu)
        return RoutingOCRProvider(
            primary=paddle,
            hebrew_fallback=tesseract,
            primary_name="paddleocr",
        )

    if name == "tesseract":
        return tesseract

    msg = f"Unsupported OCR provider: {provider_name}"
    raise ValueError(msg)
