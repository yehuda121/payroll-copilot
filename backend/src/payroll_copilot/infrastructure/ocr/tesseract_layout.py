"""Normalize Tesseract image_to_data output into words and lines with bboxes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from payroll_copilot.application.ports.ocr import OcrLine, OcrWord
from payroll_copilot.infrastructure.ocr.confidence import average_confidence


@dataclass(frozen=True, slots=True)
class LayoutCandidate:
    """One complete OCR layout result for a PSM candidate."""

    words: tuple[OcrWord, ...]
    lines: tuple[OcrLine, ...]
    text: str
    mean_confidence: float | None
    valid_word_count: int
    non_empty_line_count: int


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_tesseract_words(
    data: dict[str, Any],
    *,
    min_confidence: float = 0.0,
) -> list[OcrWord]:
    """Extract valid word records with ``(x, y, width, height)`` bboxes."""
    texts = data.get("text") or []
    n = len(texts)
    confs = data.get("conf") or []
    lefts = data.get("left") or []
    tops = data.get("top") or []
    widths = data.get("width") or []
    heights = data.get("height") or []
    block_nums = data.get("block_num") or []
    par_nums = data.get("par_num") or []
    line_nums = data.get("line_num") or []
    word_nums = data.get("word_num") or []
    words: list[OcrWord] = []

    for i in range(n):
        text = (texts[i] or "").strip() if i < len(texts) else ""
        if not text:
            continue
        try:
            conf_raw = float(confs[i])
        except (TypeError, ValueError, IndexError):
            continue
        if conf_raw < 0 or conf_raw != conf_raw:  # negative or NaN
            continue
        conf_norm = conf_raw / 100.0
        if conf_norm < min_confidence:
            continue

        try:
            left = float(lefts[i])
            top = float(tops[i])
            width = float(widths[i])
            height = float(heights[i])
        except (TypeError, ValueError, IndexError):
            continue
        if width <= 0 or height <= 0:
            continue
        if left != left or top != top:  # NaN guard
            continue

        words.append(
            OcrWord(
                text=text,
                confidence=conf_norm,
                bbox=(left, top, width, height),
                block_number=_as_int(block_nums[i] if i < len(block_nums) else 0),
                paragraph_number=_as_int(par_nums[i] if i < len(par_nums) else 0),
                line_number=_as_int(line_nums[i] if i < len(line_nums) else 0),
                word_number=_as_int(word_nums[i] if i < len(word_nums) else 0),
            )
        )
    return words


def union_bbox(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    """Union of ``(x, y, width, height)`` boxes → enclosing ``(x, y, width, height)``."""
    if not boxes:
        return None
    min_x = min(x for x, _y, _w, _h in boxes)
    min_y = min(y for _x, y, _w, _h in boxes)
    max_right = max(x + w for x, _y, w, _h in boxes)
    max_bottom = max(y + h for _x, y, _w, h in boxes)
    width = max_right - min_x
    height = max_bottom - min_y
    if width <= 0 or height <= 0:
        return None
    return (min_x, min_y, width, height)


def group_words_into_lines(words: list[OcrWord]) -> list[OcrLine]:
    """Group by Tesseract block/par/line; order lines by vertical position then keys."""
    buckets: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        key = (word.block_number, word.paragraph_number, word.line_number)
        buckets.setdefault(key, []).append(word)

    prepared: list[tuple[float, tuple[int, int, int], OcrLine]] = []
    for key, group in buckets.items():
        ordered = sorted(group, key=lambda w: (w.word_number, w.bbox[0], w.bbox[1]))
        line_text = " ".join(w.text for w in ordered).strip()
        if not line_text:
            continue
        confidences = [w.confidence for w in ordered if w.confidence is not None]
        bbox = union_bbox([w.bbox for w in ordered])
        line = OcrLine(
            text=line_text,
            confidence=average_confidence(confidences),
            bbox=bbox,
            words=tuple(ordered),
        )
        y_key = bbox[1] if bbox is not None else float(key[2])
        prepared.append((y_key, key, line))

    prepared.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in prepared]


def build_layout_candidate(
    data: dict[str, Any],
    *,
    min_confidence: float = 0.0,
) -> LayoutCandidate:
    words = parse_tesseract_words(data, min_confidence=min_confidence)
    lines = group_words_into_lines(words)
    text = "\n".join(line.text for line in lines if line.text).strip()
    confidences = [w.confidence for w in words if w.confidence is not None]
    return LayoutCandidate(
        words=tuple(words),
        lines=tuple(lines),
        text=text,
        mean_confidence=average_confidence(confidences),
        valid_word_count=len(words),
        non_empty_line_count=sum(1 for line in lines if line.text.strip()),
    )
