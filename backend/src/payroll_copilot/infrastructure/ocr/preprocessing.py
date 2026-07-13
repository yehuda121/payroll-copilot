"""Deterministic document image preprocessing for Tesseract OCR.

Production-oriented, configuration-driven pipeline. Does not invent OCR text
or confidence. Does not mutate source bytes or the caller's Pillow image.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps
from PIL.Image import DecompressionBombError

from payroll_copilot.application.exceptions import (
    OcrCorruptedDocumentError,
    OcrProviderError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OcrPreprocessingConfig:
    """Immutable preprocessing settings (injected from application Settings)."""

    enabled: bool = True
    target_long_edge: int = 2000
    max_scale_factor: float = 3.0
    max_pixels: int = 20_000_000
    contrast_factor: float = 1.4
    sharpness_factor: float = 1.3


@dataclass(frozen=True, slots=True)
class PreprocessingResult:
    """Processed image plus diagnostics suitable for debug logging."""

    image: Image.Image
    original_size: tuple[int, int]
    processed_size: tuple[int, int]
    original_mode: str
    processed_mode: str
    scale_factor: float
    duration_ms: float
    enabled: bool


class DocumentImagePreprocessor:
    """Thread-safe, deterministic preprocessor for document OCR images.

    Accepts a Pillow image and returns a new processed image. Never mutates
    the input. When disabled, returns an independent copy of the input so
    callers may safely close either image.
    """

    def __init__(self, config: OcrPreprocessingConfig) -> None:
        self._config = config

    @property
    def config(self) -> OcrPreprocessingConfig:
        return self._config

    def process(self, image: Image.Image) -> PreprocessingResult:
        started = time.perf_counter()
        if image.size[0] <= 0 or image.size[1] <= 0:
            raise OcrCorruptedDocumentError("Image has invalid dimensions.")

        original_size = (int(image.size[0]), int(image.size[1]))
        original_mode = image.mode
        self._assert_pixel_budget(original_size[0], original_size[1], stage="input")

        if not self._config.enabled:
            # Compatible with the legacy direct path: no transforms, independent copy.
            copy = image.copy()
            duration_ms = (time.perf_counter() - started) * 1000.0
            result = PreprocessingResult(
                image=copy,
                original_size=original_size,
                processed_size=(int(copy.size[0]), int(copy.size[1])),
                original_mode=original_mode,
                processed_mode=copy.mode,
                scale_factor=1.0,
                duration_ms=duration_ms,
                enabled=False,
            )
            self._log_result(result)
            return result

        try:
            working = ImageOps.exif_transpose(image)
            if working is None:
                working = image.copy()
            elif working is image:
                working = image.copy()

            working = self._flatten_alpha(working)
            working = working.convert("L")
            working, scale_factor = self._upscale_if_needed(working)
            working = ImageEnhance.Contrast(working).enhance(self._config.contrast_factor)
            working = ImageEnhance.Sharpness(working).enhance(self._config.sharpness_factor)
        except (OcrCorruptedDocumentError, OcrProviderError):
            raise
        except DecompressionBombError as exc:
            raise OcrProviderError(
                "Image exceeds safe pixel limits for OCR preprocessing."
            ) from exc
        except MemoryError as exc:
            raise OcrProviderError("Insufficient memory to preprocess image for OCR.") from exc
        except OSError as exc:
            raise OcrCorruptedDocumentError(f"Image could not be preprocessed: {exc}") from exc
        except ValueError as exc:
            raise OcrCorruptedDocumentError(f"Unsupported or corrupt image data: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — map unexpected failures into OCR errors
            raise OcrProviderError(f"Image preprocessing failed: {exc}") from exc

        duration_ms = (time.perf_counter() - started) * 1000.0
        result = PreprocessingResult(
            image=working,
            original_size=original_size,
            processed_size=(int(working.size[0]), int(working.size[1])),
            original_mode=original_mode,
            processed_mode=working.mode,
            scale_factor=scale_factor,
            duration_ms=duration_ms,
            enabled=True,
        )
        self._log_result(result)
        return result

    def _flatten_alpha(self, image: Image.Image) -> Image.Image:
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        if image.mode == "P":
            return image.convert("RGB")
        if image.mode in {"L", "RGB"}:
            return image.copy()
        try:
            return image.convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise OcrCorruptedDocumentError(
                f"Unsupported image mode for OCR preprocessing: {image.mode}"
            ) from exc

    def _upscale_if_needed(self, image: Image.Image) -> tuple[Image.Image, float]:
        width, height = image.size
        long_edge = max(width, height)
        target = max(1, int(self._config.target_long_edge))
        max_scale = max(1.0, float(self._config.max_scale_factor))

        if long_edge >= target:
            return image, 1.0

        scale = min(target / float(long_edge), max_scale)
        if scale <= 1.0:
            return image, 1.0

        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))
        self._assert_pixel_budget(new_width, new_height, stage="upscale")

        resized = image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS)
        actual_scale = new_width / float(width) if width else scale
        return resized, actual_scale

    def _assert_pixel_budget(self, width: int, height: int, *, stage: str) -> None:
        pixels = int(width) * int(height)
        limit = int(self._config.max_pixels)
        if pixels > limit:
            raise OcrProviderError(
                f"Image {stage} dimensions {width}x{height} ({pixels} pixels) "
                f"exceed the configured OCR safety limit of {limit} pixels."
            )

    @staticmethod
    def _log_result(result: PreprocessingResult) -> None:
        logger.debug(
            "ocr_image_preprocessing enabled=%s original_size=%sx%s processed_size=%sx%s "
            "original_mode=%s processed_mode=%s scale_factor=%.4f duration_ms=%.2f",
            result.enabled,
            result.original_size[0],
            result.original_size[1],
            result.processed_size[0],
            result.processed_size[1],
            result.original_mode,
            result.processed_mode,
            result.scale_factor,
            result.duration_ms,
        )


def preprocessing_config_from_settings(settings: object) -> OcrPreprocessingConfig:
    """Build config from application Settings without reading env vars here."""
    return OcrPreprocessingConfig(
        enabled=bool(getattr(settings, "ocr_preprocessing_enabled", True)),
        target_long_edge=int(getattr(settings, "ocr_preprocessing_target_long_edge", 2000)),
        max_scale_factor=float(getattr(settings, "ocr_preprocessing_max_scale_factor", 3.0)),
        max_pixels=int(getattr(settings, "ocr_preprocessing_max_pixels", 20_000_000)),
        contrast_factor=float(getattr(settings, "ocr_preprocessing_contrast_factor", 1.4)),
        sharpness_factor=float(getattr(settings, "ocr_preprocessing_sharpness_factor", 1.3)),
    )
