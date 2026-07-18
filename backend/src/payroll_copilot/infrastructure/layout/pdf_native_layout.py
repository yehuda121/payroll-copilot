"""Native PDF layout extraction via PyMuPDF (geometry-preserving).

Payroll-agnostic: tokens, boxes, blocks, and reading order only.
"""

from __future__ import annotations

import logging
from typing import Any

import fitz

from payroll_copilot.application.ports.layout import LAYOUT_SNAPSHOT_SCHEMA_VERSION

logger = logging.getLogger(__name__)


def _xywh(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [float(x0), float(y0), float(max(0.0, x1 - x0)), float(max(0.0, y1 - y0))]


def _bbox_nonzero(bbox: list[float] | None) -> bool:
    if not bbox or len(bbox) != 4:
        return False
    return bbox[2] > 0 and bbox[3] > 0


def extract_native_pdf_layout(
    pdf_bytes: bytes,
    *,
    include_words: bool = True,
    max_pages: int = 20,
    max_words: int = 8_000,
    max_lines: int = 2_000,
) -> dict[str, Any] | None:
    """Extract page/block/line/word geometry from a PDF text layer.

    Returns None when the document cannot be opened or yields no layout tokens.
    Does not rasterize and does not invent missing text.
    """
    if not pdf_bytes:
        return None

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        logger.info("layout_snapshot pdf_native_open_failed")
        return None

    warnings: list[str] = []
    pages_out: list[dict[str, Any]] = []
    total_words = 0
    total_lines = 0
    truncated = False

    try:
        if document.page_count == 0:
            return None

        page_limit = min(document.page_count, max(1, max_pages))
        if document.page_count > page_limit:
            warnings.append("layout_snapshot_pages_truncated")
            truncated = True

        for page_index in range(page_limit):
            if total_words >= max_words or total_lines >= max_lines:
                warnings.append("layout_snapshot_budget_exhausted")
                truncated = True
                break

            page = document.load_page(page_index)
            page_number = page_index + 1
            rect = page.rect
            page_width = float(rect.width)
            page_height = float(rect.height)

            # words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            raw_words = page.get_text("words") or []
            raw_dict = page.get_text("dict") or {}

            blocks_out: list[dict[str, Any]] = []
            block_line_ids: dict[int, list[str]] = {}

            for block in raw_dict.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                block_no = int(block.get("number", len(blocks_out)))
                bbox_vals = block.get("bbox")
                block_bbox = None
                if isinstance(bbox_vals, (list, tuple)) and len(bbox_vals) == 4:
                    block_bbox = _xywh(
                        float(bbox_vals[0]),
                        float(bbox_vals[1]),
                        float(bbox_vals[2]),
                        float(bbox_vals[3]),
                    )
                block_id = f"p{page_number}_b{block_no}"
                block_line_ids[block_no] = []
                blocks_out.append(
                    {
                        "id": block_id,
                        "block_number": block_no,
                        "bbox": block_bbox,
                        "type": int(block.get("type", 0)),
                        "line_ids": block_line_ids[block_no],
                    }
                )

            # Group words by (block_no, line_no) preserving PDF reading order.
            line_buckets: dict[tuple[int, int], list[tuple[int, tuple]]] = {}
            for word in raw_words:
                if not isinstance(word, (list, tuple)) or len(word) < 8:
                    continue
                block_no = int(word[5])
                line_no = int(word[6])
                word_no = int(word[7])
                line_buckets.setdefault((block_no, line_no), []).append((word_no, word))

            lines_out: list[dict[str, Any]] = []
            words_out: list[dict[str, Any]] = []
            reading_index = 0

            for (block_no, line_no), members in sorted(line_buckets.items()):
                if total_lines >= max_lines:
                    warnings.append("layout_snapshot_lines_truncated")
                    truncated = True
                    break

                members_sorted = [item[1] for item in sorted(members, key=lambda pair: pair[0])]
                line_id = f"p{page_number}_b{block_no}_l{line_no}"
                line_word_ids: list[str] = []
                texts: list[str] = []
                xs0: list[float] = []
                ys0: list[float] = []
                xs1: list[float] = []
                ys1: list[float] = []

                for word in members_sorted:
                    if include_words and total_words >= max_words:
                        warnings.append("layout_snapshot_words_truncated")
                        truncated = True
                        break
                    text = str(word[4] or "")
                    if not text:
                        continue
                    bbox = _xywh(float(word[0]), float(word[1]), float(word[2]), float(word[3]))
                    word_id = f"{line_id}_w{int(word[7])}"
                    if include_words:
                        words_out.append(
                            {
                                "id": word_id,
                                "text": text,
                                "bbox": bbox,
                                "line_id": line_id,
                                "block_id": f"p{page_number}_b{block_no}",
                                "reading_index": reading_index,
                                "confidence": None,
                                "block_number": block_no,
                                "line_number": line_no,
                                "word_number": int(word[7]),
                            }
                        )
                        total_words += 1
                    line_word_ids.append(word_id)
                    texts.append(text)
                    xs0.append(float(word[0]))
                    ys0.append(float(word[1]))
                    xs1.append(float(word[2]))
                    ys1.append(float(word[3]))
                    reading_index += 1

                if not texts:
                    continue

                line_bbox = _xywh(min(xs0), min(ys0), max(xs1), max(ys1)) if xs0 else None
                lines_out.append(
                    {
                        "id": line_id,
                        "text": " ".join(texts),
                        "bbox": line_bbox,
                        "block_id": f"p{page_number}_b{block_no}",
                        "reading_index": len(lines_out),
                        "confidence": None,
                        "word_ids": line_word_ids if include_words else [],
                        "block_number": block_no,
                        "line_number": line_no,
                    }
                )
                if block_no in block_line_ids:
                    block_line_ids[block_no].append(line_id)
                total_lines += 1

            # Prefer dict-derived blocks; synthesize from words when dict empty.
            if not blocks_out and lines_out:
                seen_blocks: dict[int, dict[str, Any]] = {}
                for line in lines_out:
                    bno = int(line["block_number"])
                    bid = str(line["block_id"])
                    entry = seen_blocks.get(bno)
                    if entry is None:
                        entry = {
                            "id": bid,
                            "block_number": bno,
                            "bbox": line.get("bbox"),
                            "type": 0,
                            "line_ids": [],
                        }
                        seen_blocks[bno] = entry
                    entry["line_ids"].append(line["id"])
                blocks_out = [seen_blocks[k] for k in sorted(seen_blocks)]

            pages_out.append(
                {
                    "page": page_number,
                    "width": page_width,
                    "height": page_height,
                    "blocks": blocks_out,
                    "lines": lines_out,
                    "words": words_out if include_words else [],
                }
            )

        nonzero_tokens = 0
        for page in pages_out:
            for line in page.get("lines") or []:
                if _bbox_nonzero(line.get("bbox")):
                    nonzero_tokens += 1
            for word in page.get("words") or []:
                if _bbox_nonzero(word.get("bbox")):
                    nonzero_tokens += 1

        if nonzero_tokens == 0 and not any((page.get("lines") or []) for page in pages_out):
            return None

        if nonzero_tokens == 0:
            warnings.append("layout_snapshot_zero_bboxes")

        return {
            "schema_version": LAYOUT_SNAPSHOT_SCHEMA_VERSION,
            "provider": "hybrid_layout_v1",
            "source": "pdf_native",
            "coordinate_format": "xywh",
            "coordinate_space": "pdf_points",
            "engine": "pymupdf",
            "page_count": len(pages_out),
            "truncated": truncated,
            "pages": pages_out,
            "warnings": warnings,
        }
    finally:
        document.close()
