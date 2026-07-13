"""Unit tests for Tesseract layout, multi-PSM scoring, and bounding boxes."""

from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from payroll_copilot.application.exceptions import OcrProviderError
from payroll_copilot.application.ports.ocr import OcrWord
from payroll_copilot.infrastructure.ocr.language import to_tesseract_lang
from payroll_copilot.infrastructure.ocr.preprocessing import (
    DocumentImagePreprocessor,
    OcrPreprocessingConfig,
    PreprocessingResult,
)
from payroll_copilot.infrastructure.ocr.tesseract_config import (
    TesseractStrategyConfig,
    parse_psm_candidates,
)
from payroll_copilot.infrastructure.ocr.tesseract_layout import (
    LayoutCandidate,
    build_layout_candidate,
    group_words_into_lines,
    parse_tesseract_words,
    union_bbox,
)
from payroll_copilot.infrastructure.ocr.tesseract_scoring import (
    CandidateMetrics,
    score_candidate_metrics,
    score_layout_candidate,
    select_best_candidate,
)
from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider
from payroll_copilot.presentation.api.routes.ocr import _to_response


def _word(
    text: str,
    *,
    conf: float,
    bbox: tuple[float, float, float, float],
    block: int = 1,
    par: int = 1,
    line: int = 1,
    word_num: int = 1,
) -> OcrWord:
    return OcrWord(
        text=text,
        confidence=conf,
        bbox=bbox,
        block_number=block,
        paragraph_number=par,
        line_number=line,
        word_number=word_num,
    )


def test_word_bbox_mapping_from_tesseract_data() -> None:
    data = {
        "text": ["Hello", ""],
        "conf": ["91", "-1"],
        "left": ["10", "0"],
        "top": ["20", "0"],
        "width": ["30", "0"],
        "height": ["12", "0"],
        "block_num": ["1", "1"],
        "par_num": ["1", "1"],
        "line_num": ["1", "1"],
        "word_num": ["1", "2"],
    }
    words = parse_tesseract_words(data)
    assert len(words) == 1
    assert words[0].text == "Hello"
    assert words[0].confidence == pytest.approx(0.91)
    assert words[0].bbox == (10.0, 20.0, 30.0, 12.0)


def test_line_bbox_union() -> None:
    boxes = [(10.0, 20.0, 30.0, 10.0), (50.0, 22.0, 40.0, 12.0)]
    assert union_bbox(boxes) == (10.0, 20.0, 80.0, 14.0)

    words = [
        _word("A", conf=0.9, bbox=(10, 20, 30, 10), word_num=1),
        _word("B", conf=0.8, bbox=(50, 22, 40, 12), word_num=2),
    ]
    lines = group_words_into_lines(words)
    assert len(lines) == 1
    assert lines[0].bbox == (10.0, 20.0, 80.0, 14.0)
    assert lines[0].text == "A B"


def test_invalid_tokens_ignored() -> None:
    data = {
        "text": ["", "ok", "bad", "geo"],
        "conf": ["80", "-5", "nan", "70"],
        "left": ["0", "1", "2", "3"],
        "top": ["0", "1", "2", "3"],
        "width": ["1", "2", "3", "0"],
        "height": ["1", "2", "3", "5"],
        "block_num": ["1", "1", "1", "1"],
        "par_num": ["1", "1", "1", "1"],
        "line_num": ["1", "1", "1", "1"],
        "word_num": ["1", "2", "3", "4"],
    }
    words = parse_tesseract_words(data)
    assert [w.text for w in words] == []


def test_line_confidence_mean_of_valid_words() -> None:
    words = [
        _word("A", conf=0.5, bbox=(0, 0, 5, 5), word_num=1),
        _word("B", conf=1.0, bbox=(6, 0, 5, 5), word_num=2),
    ]
    lines = group_words_into_lines(words)
    assert lines[0].confidence == pytest.approx(0.75)


def test_candidate_scoring_determinism() -> None:
    metrics = CandidateMetrics(
        mean_confidence=0.7,
        valid_word_count=20,
        non_empty_line_count=8,
        alnum_ratio=0.9,
        script_ratio=0.95,
        duplicate_ratio=0.1,
        single_char_ratio=0.05,
        punct_ratio=0.1,
        script_mix_penalty=0.0,
        coverage_score=0.6,
    )
    assert score_candidate_metrics(metrics) == score_candidate_metrics(metrics)


def test_cleaner_candidate_scores_higher() -> None:
    clean = LayoutCandidate(
        words=(
            _word("Invoice", conf=0.92, bbox=(10, 10, 40, 12), word_num=1),
            _word("Total", conf=0.9, bbox=(60, 10, 30, 12), word_num=2),
            _word("123", conf=0.95, bbox=(100, 10, 20, 12), word_num=3),
        ),
        lines=(),
        text="Invoice Total 123",
        mean_confidence=0.923,
        valid_word_count=3,
        non_empty_line_count=1,
    )
    noisy = LayoutCandidate(
        words=(
            _word("@@", conf=0.2, bbox=(10, 10, 8, 8), word_num=1),
            _word("#", conf=0.15, bbox=(20, 10, 5, 5), word_num=2),
            _word("~~", conf=0.1, bbox=(30, 10, 5, 5), word_num=3),
        ),
        lines=(),
        text="@@ # ~~",
        mean_confidence=0.15,
        valid_word_count=3,
        non_empty_line_count=1,
    )
    clean_score = score_layout_candidate(clean, tess_lang="eng", image_width=200, image_height=100)
    noisy_score = score_layout_candidate(noisy, tess_lang="eng", image_width=200, image_height=100)
    assert clean_score > noisy_score


def test_tie_breaking_prefers_lower_psm() -> None:
    layout = LayoutCandidate(
        words=(_word("A", conf=0.8, bbox=(0, 0, 5, 5)),),
        lines=(),
        text="A",
        mean_confidence=0.8,
        valid_word_count=1,
        non_empty_line_count=1,
    )
    scored = [
        (6, 0.5, 0.8, 1, layout),
        (3, 0.5, 0.8, 1, layout),
        (4, 0.5, 0.8, 1, layout),
    ]
    psm, score, selected = select_best_candidate(scored)
    assert psm == 3
    assert score == 0.5
    assert selected is layout


def test_psm_configuration_parsing() -> None:
    assert parse_psm_candidates("3,4,6,11", max_candidates=4) == (3, 4, 6, 11)
    assert parse_psm_candidates("3,3,4,4,6", max_candidates=4) == (3, 4, 6)
    assert parse_psm_candidates("3,4,6,11,12", max_candidates=3) == (3, 4, 6)
    with pytest.raises(OcrProviderError):
        parse_psm_candidates("3,99", max_candidates=4)
    with pytest.raises(OcrProviderError):
        parse_psm_candidates("abc", max_candidates=4)


def test_language_mappings_unchanged() -> None:
    assert to_tesseract_lang("auto") == "heb+eng"
    assert to_tesseract_lang("he") == "heb+eng"
    assert to_tesseract_lang("en") == "eng"
    assert to_tesseract_lang("ar") == "ara+eng"


@pytest.mark.asyncio
async def test_candidate_failure_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _fake_image_to_data(image: Image.Image, **kwargs: Any) -> dict[str, list[Any]]:
        config = str(kwargs.get("config") or "")
        calls.append(config)
        if "--psm 3" in config:
            raise RuntimeError("simulated psm3 failure")
        return {
            "text": ["Hello", "World"],
            "conf": ["90", "80"],
            "left": [1, 40],
            "top": [2, 2],
            "width": [30, 35],
            "height": [10, 10],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "word_num": [1, 2],
        }

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _fake_image_to_data,
    )
    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
        strategy=TesseractStrategyConfig(
            multi_psm_enabled=True,
            psm_candidates=(3, 4),
            default_oem=3,
            max_candidates=4,
        ),
    )
    image = Image.new("RGB", (80, 40), color=(255, 255, 255))
    buf = __import__("io").BytesIO()
    image.save(buf, format="PNG")
    result = await provider.extract(
        content=buf.getvalue(),
        media_type="image/png",
        filename="x.png",
        language="en",
    )
    assert "Hello" in result.raw_text
    assert any("selected_psm=4" in w for w in result.warnings)
    assert any("--psm 3" in c for c in calls)
    assert any("--psm 4" in c for c in calls)


@pytest.mark.asyncio
async def test_all_candidates_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> dict[str, list[Any]]:
        raise RuntimeError("always fails")

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _boom,
    )
    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
        strategy=TesseractStrategyConfig(psm_candidates=(3, 4), max_candidates=2),
    )
    image = Image.new("L", (20, 20), color=255)
    buf = __import__("io").BytesIO()
    image.save(buf, format="PNG")
    with pytest.raises(OcrProviderError):
        await provider.extract(
            content=buf.getvalue(),
            media_type="image/png",
            filename="x.png",
            language="en",
        )


@pytest.mark.asyncio
async def test_preprocessing_called_once_for_multi_psm(monkeypatch: pytest.MonkeyPatch) -> None:
    process_calls = {"n": 0}
    tess_calls = {"n": 0}

    class _CountingPreprocessor(DocumentImagePreprocessor):
        def process(self, image: Image.Image) -> PreprocessingResult:  # type: ignore[override]
            process_calls["n"] += 1
            return super().process(image)

    def _fake_image_to_data(image: Image.Image, **kwargs: Any) -> dict[str, list[Any]]:
        tess_calls["n"] += 1
        return {
            "text": ["A"],
            "conf": ["90"],
            "left": [1],
            "top": [1],
            "width": [5],
            "height": [5],
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
        preprocessor=_CountingPreprocessor(OcrPreprocessingConfig(enabled=False)),
        strategy=TesseractStrategyConfig(psm_candidates=(3, 4, 6, 11), max_candidates=4),
    )
    image = Image.new("RGB", (30, 20), color=(255, 255, 255))
    buf = __import__("io").BytesIO()
    image.save(buf, format="PNG")
    await provider.extract(
        content=buf.getvalue(),
        media_type="image/png",
        filename="x.png",
        language="en",
    )
    assert process_calls["n"] == 1
    assert tess_calls["n"] == 4


@pytest.mark.asyncio
async def test_line_bbox_api_output_and_schema_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_image_to_data(image: Image.Image, **kwargs: Any) -> dict[str, list[Any]]:
        return {
            "text": ["Alpha", "Beta"],
            "conf": ["88", "77"],
            "left": [5, 40],
            "top": [8, 9],
            "width": [20, 25],
            "height": [10, 11],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "word_num": [1, 2],
        }

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.pytesseract.image_to_data",
        _fake_image_to_data,
    )
    provider = TesseractOCRProvider(
        preprocessor=DocumentImagePreprocessor(OcrPreprocessingConfig(enabled=False)),
        strategy=TesseractStrategyConfig(psm_candidates=(4,), max_candidates=1),
    )
    image = Image.new("RGB", (100, 40), color=(255, 255, 255))
    buf = __import__("io").BytesIO()
    image.save(buf, format="PNG")
    result = await provider.extract(
        content=buf.getvalue(),
        media_type="image/png",
        filename="x.png",
        language="en",
    )
    assert result.pages[0].lines[0].bbox is not None
    assert all(line.bbox is not None for line in result.pages[0].lines)
    assert result.pages[0].words
    assert result.pages[0].lines[0].words

    payload = _to_response(result).model_dump()
    for key in (
        "engine",
        "language_requested",
        "language_effective",
        "overall_confidence",
        "raw_text",
        "warnings",
        "pages",
    ):
        assert key in payload
    assert payload["pages"][0]["lines"][0]["bbox"] is not None
    assert payload["pages"][0]["lines"][0]["words"]
    assert payload["pages"][0]["words"]


def test_build_layout_candidate_orders_lines_by_y() -> None:
    data = {
        "text": ["top", "bottom"],
        "conf": ["90", "90"],
        "left": [1, 1],
        "top": [5, 50],
        "width": [10, 10],
        "height": [8, 8],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [2, 1],
        "word_num": [1, 1],
    }
    layout = build_layout_candidate(data)
    assert [line.text for line in layout.lines] == ["top", "bottom"]
