"""Build layout snapshots from OCRResult geometry (raster / OCR path)."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.layout import LAYOUT_SNAPSHOT_SCHEMA_VERSION
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage, OcrWord


def _bbox_list(bbox: tuple[float, float, float, float] | None) -> list[float] | None:
    if bbox is None:
        return None
    return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]


def _bbox_nonzero(bbox: list[float] | None) -> bool:
    if not bbox or len(bbox) != 4:
        return False
    return bbox[2] > 0 and bbox[3] > 0


def layout_snapshot_from_ocr(
    ocr_result: OCRResult,
    *,
    include_words: bool = True,
    max_pages: int = 20,
    max_words: int = 8_000,
    max_lines: int = 2_000,
) -> dict[str, Any]:
    """Project existing OCR page/line/word geometry into a layout_snapshot.

    Preserves only structure present on OCRResult. Does not invent boxes.
    """
    warnings: list[str] = list(ocr_result.warnings or ())
    pages_out: list[dict[str, Any]] = []
    total_words = 0
    total_lines = 0
    truncated = False

    pages = list(ocr_result.pages or ())
    page_limit = min(len(pages), max(1, max_pages)) if pages else 0
    if len(pages) > page_limit:
        warnings.append("layout_snapshot_pages_truncated")
        truncated = True

    for page in pages[:page_limit]:
        if total_lines >= max_lines or total_words >= max_words:
            warnings.append("layout_snapshot_budget_exhausted")
            truncated = True
            break
        page_out, words_added, lines_added, page_truncated = _page_from_ocr(
            page,
            include_words=include_words,
            max_words=max_words - total_words,
            max_lines=max_lines - total_lines,
            reading_index_start=total_words,
        )
        total_words += words_added
        total_lines += lines_added
        if page_truncated:
            truncated = True
            warnings.append("layout_snapshot_page_budget_truncated")
        pages_out.append(page_out)

    nonzero = 0
    for page in pages_out:
        for line in page.get("lines") or []:
            if _bbox_nonzero(line.get("bbox")):
                nonzero += 1
        for word in page.get("words") or []:
            if _bbox_nonzero(word.get("bbox")):
                nonzero += 1
    if nonzero == 0:
        warnings.append("layout_snapshot_zero_bboxes")

    engine = ocr_result.engine or "ocr"
    coordinate_space = "processed_image_pixels"
    if "pdf_text" in engine:
        coordinate_space = "unknown"

    return {
        "schema_version": LAYOUT_SNAPSHOT_SCHEMA_VERSION,
        "provider": "hybrid_layout_v1",
        "source": "ocr_result",
        "coordinate_format": "xywh",
        "coordinate_space": coordinate_space,
        "engine": engine,
        "page_count": len(pages_out),
        "truncated": truncated,
        "pages": pages_out,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _page_from_ocr(
    page: OcrPage,
    *,
    include_words: bool,
    max_words: int,
    max_lines: int,
    reading_index_start: int,
) -> tuple[dict[str, Any], int, int, bool]:
    page_number = int(page.page)
    lines_src: list[OcrLine] = list(page.lines or ())
    words_src: list[OcrWord] = list(page.words or ())
    truncated = False

    if not lines_src and words_src:
        lines_src = _synthesize_lines_from_words(words_src)

    blocks: dict[int, dict[str, Any]] = {}
    lines_out: list[dict[str, Any]] = []
    words_out: list[dict[str, Any]] = []
    local_words = 0
    local_lines = 0
    reading_index = reading_index_start
    used_line_ids: set[str] = set()

    for line_idx, line in enumerate(lines_src):
        if local_lines >= max_lines:
            truncated = True
            break

        line_words = list(line.words or ())
        block_no = int(line_words[0].block_number) if line_words else 0
        line_no = int(line_words[0].line_number) if line_words else line_idx
        line_id = f"p{page_number}_b{block_no}_l{line_no}"
        if line_id in used_line_ids:
            line_id = f"{line_id}_{line_idx}"
        used_line_ids.add(line_id)

        word_ids: list[str] = []
        for word_idx, word in enumerate(line_words):
            if not include_words:
                break
            if local_words >= max_words:
                truncated = True
                break
            word_id = f"{line_id}_w{int(word.word_number) if word.word_number else word_idx}"
            words_out.append(
                {
                    "id": word_id,
                    "text": word.text or "",
                    "bbox": _bbox_list(word.bbox),
                    "line_id": line_id,
                    "block_id": f"p{page_number}_b{int(word.block_number)}",
                    "reading_index": reading_index,
                    "confidence": word.confidence,
                    "block_number": int(word.block_number),
                    "line_number": int(word.line_number),
                    "word_number": int(word.word_number),
                }
            )
            word_ids.append(word_id)
            local_words += 1
            reading_index += 1

        line_bbox = _bbox_list(line.bbox)
        lines_out.append(
            {
                "id": line_id,
                "text": line.text or "",
                "bbox": line_bbox,
                "block_id": f"p{page_number}_b{block_no}",
                "reading_index": len(lines_out),
                "confidence": line.confidence,
                "word_ids": word_ids,
                "block_number": block_no,
                "line_number": line_no,
            }
        )
        local_lines += 1

        block = blocks.get(block_no)
        if block is None:
            block = {
                "id": f"p{page_number}_b{block_no}",
                "block_number": block_no,
                "bbox": line_bbox,
                "type": 0,
                "line_ids": [],
            }
            blocks[block_no] = block
        block["line_ids"].append(line_id)

    if include_words and not any(line.words for line in (page.lines or ())) and words_src:
        for word_idx, word in enumerate(words_src):
            if local_words >= max_words:
                truncated = True
                break
            line_id = f"p{page_number}_b{int(word.block_number)}_l{int(word.line_number)}"
            word_id = f"{line_id}_w{int(word.word_number) if word.word_number else word_idx}"
            if any(item["id"] == word_id for item in words_out):
                continue
            words_out.append(
                {
                    "id": word_id,
                    "text": word.text or "",
                    "bbox": _bbox_list(word.bbox),
                    "line_id": line_id,
                    "block_id": f"p{page_number}_b{int(word.block_number)}",
                    "reading_index": reading_index,
                    "confidence": word.confidence,
                    "block_number": int(word.block_number),
                    "line_number": int(word.line_number),
                    "word_number": int(word.word_number),
                }
            )
            local_words += 1
            reading_index += 1

    return (
        {
            "page": page_number,
            "width": None,
            "height": None,
            "blocks": [blocks[k] for k in sorted(blocks)],
            "lines": lines_out,
            "words": words_out if include_words else [],
        },
        local_words,
        local_lines,
        truncated,
    )


def _synthesize_lines_from_words(words: list[OcrWord]) -> list[OcrLine]:
    buckets: dict[tuple[int, int], list[OcrWord]] = {}
    for word in words:
        key = (int(word.block_number), int(word.line_number))
        buckets.setdefault(key, []).append(word)

    lines: list[OcrLine] = []
    for key in sorted(buckets):
        members = sorted(buckets[key], key=lambda item: int(item.word_number))
        text = " ".join(item.text for item in members if item.text)
        confidences = [item.confidence for item in members if item.confidence is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        xs0 = [item.bbox[0] for item in members]
        ys0 = [item.bbox[1] for item in members]
        xs1 = [item.bbox[0] + item.bbox[2] for item in members]
        ys1 = [item.bbox[1] + item.bbox[3] for item in members]
        bbox = (
            min(xs0),
            min(ys0),
            max(xs1) - min(xs0),
            max(ys1) - min(ys0),
        )
        lines.append(
            OcrLine(
                text=text,
                confidence=confidence,
                bbox=bbox,
                words=tuple(members),
            )
        )
    return lines
