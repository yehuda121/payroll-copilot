"""Unit tests for Tesseract OCR image preprocessing."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from payroll_copilot.application.exceptions import OcrProviderError
from payroll_copilot.infrastructure.ocr.preprocessing import (
    DocumentImagePreprocessor,
    OcrPreprocessingConfig,
)
from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider

FIXTURE_PNG = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "documents"
    / "payslips"
    / "valid"
    / "payslip_valid_2026_06_employee_001.png"
)


def _rgba_sample(size: tuple[int, int] = (40, 30)) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, size[0] - 6, size[1] - 6), fill=(10, 20, 30, 200))
    return image


def test_rgba_flattens_to_grayscale_l() -> None:
    preprocessor = DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=True, target_long_edge=40))
    source = _rgba_sample()
    result = preprocessor.process(source)

    assert result.processed_mode == "L"
    assert result.image.mode == "L"
    assert source.mode == "RGBA"


def test_small_image_upscales_preserving_aspect_within_max_scale() -> None:
    config = OcrPreprocessingConfig(
        enabled=True,
        target_long_edge=2000,
        max_scale_factor=3.0,
        contrast_factor=1.0,
        sharpness_factor=1.0,
    )
    preprocessor = DocumentImagePreprocessor(config)
    source = Image.new("RGB", (100, 200), color=(240, 240, 240))
    result = preprocessor.process(source)

    assert result.scale_factor <= config.max_scale_factor + 1e-9
    assert result.processed_size[0] > source.size[0]
    assert result.processed_size[1] > source.size[1]
    original_ratio = source.size[0] / source.size[1]
    processed_ratio = result.processed_size[0] / result.processed_size[1]
    assert processed_ratio == pytest.approx(original_ratio, rel=1e-3, abs=1e-3)


def test_large_image_is_not_downscaled() -> None:
    config = OcrPreprocessingConfig(
        enabled=True,
        target_long_edge=2000,
        max_scale_factor=3.0,
        contrast_factor=1.0,
        sharpness_factor=1.0,
    )
    preprocessor = DocumentImagePreprocessor(config)
    source = Image.new("RGB", (3000, 2000), color=(255, 255, 255))
    result = preprocessor.process(source)

    assert result.scale_factor == 1.0
    assert result.processed_size == (3000, 2000)


def test_pixel_safety_limit_rejects_unsafe_upscale() -> None:
    config = OcrPreprocessingConfig(
        enabled=True,
        target_long_edge=10_000,
        max_scale_factor=50.0,
        max_pixels=50_000,
        contrast_factor=1.0,
        sharpness_factor=1.0,
    )
    preprocessor = DocumentImagePreprocessor(config)
    source = Image.new("RGB", (200, 200), color=(255, 255, 255))

    with pytest.raises(OcrProviderError) as exc:
        preprocessor.process(source)
    assert "safety limit" in exc.value.message


def test_disabled_preprocessing_returns_untransformed_copy() -> None:
    config = OcrPreprocessingConfig(enabled=False)
    preprocessor = DocumentImagePreprocessor(config)
    source = _rgba_sample((50, 40))
    result = preprocessor.process(source)

    assert result.enabled is False
    assert result.scale_factor == 1.0
    assert result.processed_size == source.size
    assert result.processed_mode == "RGBA"
    assert result.image is not source


def test_input_image_is_not_mutated() -> None:
    preprocessor = DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=True, target_long_edge=300))
    source = _rgba_sample((60, 80))
    before = source.tobytes()
    before_size = source.size
    before_mode = source.mode

    preprocessor.process(source)

    assert source.tobytes() == before
    assert source.size == before_size
    assert source.mode == before_mode


def test_preprocessing_is_deterministic() -> None:
    config = OcrPreprocessingConfig(
        enabled=True,
        target_long_edge=400,
        max_scale_factor=3.0,
        contrast_factor=1.4,
        sharpness_factor=1.3,
    )
    preprocessor = DocumentImagePreprocessor(config)
    source = _rgba_sample((70, 90))

    first = preprocessor.process(source)
    second = preprocessor.process(source)

    assert first.processed_size == second.processed_size
    assert first.processed_mode == second.processed_mode
    assert first.scale_factor == second.scale_factor
    assert first.image.tobytes() == second.image.tobytes()


@pytest.mark.skipif(not FIXTURE_PNG.is_file(), reason="payslip fixture PNG not present")
def test_fixture_structural_preprocessing() -> None:
    config = OcrPreprocessingConfig(
        enabled=True,
        target_long_edge=2000,
        max_scale_factor=3.0,
        max_pixels=20_000_000,
        contrast_factor=1.4,
        sharpness_factor=1.3,
    )
    preprocessor = DocumentImagePreprocessor(config)
    with Image.open(FIXTURE_PNG) as source:
        assert source.size == (493, 706)
        result = preprocessor.process(source)

    assert result.processed_mode == "L"
    assert result.processed_size[0] > 493
    assert result.processed_size[1] > 706
    original_ratio = 493 / 706
    processed_ratio = result.processed_size[0] / result.processed_size[1]
    assert processed_ratio == pytest.approx(original_ratio, rel=1e-3, abs=1e-3)
    assert result.processed_size[0] * result.processed_size[1] <= config.max_pixels
    assert result.scale_factor <= config.max_scale_factor + 1e-9


@pytest.mark.asyncio
async def test_disabled_preprocessing_keeps_tesseract_path_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_image_to_data(image: Image.Image, **kwargs: object) -> dict[str, list[object]]:
        captured["mode"] = image.mode
        captured["size"] = image.size
        captured["lang"] = kwargs.get("lang")
        return {
            "text": ["ok"],
            "conf": ["90"],
            "left": [1],
            "top": [1],
            "width": [10],
            "height": [8],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "word_num": [1],
        }

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _fake_image_to_data,
    )

    provider = TesseractOCRProvider(
        default_multi_lang="heb+eng",
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
    )
    rgba = _rgba_sample((32, 24))
    buffer = __import__("io").BytesIO()
    rgba.save(buffer, format="PNG")

    result = await provider.extract(
        content=buffer.getvalue(),
        media_type="image/png",
        filename="sample.png",
        language="auto",
    )

    assert captured["mode"] == "RGBA"
    assert captured["size"] == (32, 24)
    assert captured["lang"] == "heb+eng"
    assert result.engine == "tesseract"
    assert result.language_requested == "auto"
    assert result.language_effective == "heb+eng"
    assert result.raw_text == "ok"
    assert result.overall_confidence == pytest.approx(0.9)
