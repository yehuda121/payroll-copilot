"""Deterministic OCR → payslip-parser layout context builder.

Preserves OCR text/geometry exactly. Does not invent values or rewrite RTL.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage, OcrWord

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParserLayoutConfig:
    enabled: bool = True
    include_words: bool = True
    max_lines: int = 300
    max_words: int = 2000
    min_word_confidence: float = 0.0
    max_context_chars: int = 50_000


@dataclass(frozen=True, slots=True)
class BuiltParserContext:
    """Compact JSON-serializable OCR context for the LLM."""

    payload: dict[str, Any]
    evidence_index: dict[str, dict[str, Any]]
    context_chars: int
    line_count: int
    word_count: int
    truncated: bool


def parser_layout_config_from_settings(settings: object) -> ParserLayoutConfig:
    return ParserLayoutConfig(
        enabled=bool(getattr(settings, "payslip_parser_layout_enabled", True)),
        include_words=bool(getattr(settings, "payslip_parser_include_words", True)),
        max_lines=int(getattr(settings, "payslip_parser_max_lines", 300)),
        max_words=int(getattr(settings, "payslip_parser_max_words", 2000)),
        min_word_confidence=float(getattr(settings, "payslip_parser_min_word_confidence", 0.0)),
        max_context_chars=int(getattr(settings, "payslip_parser_max_context_chars", 50_000)),
    )


def _bbox_list(bbox: tuple[float, float, float, float] | list[float] | None) -> list[float] | None:
    if bbox is None:
        return None
    values = list(bbox)
    if len(values) != 4:
        return None
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError):
        return None


def _line_id(page_number: int, line_index: int) -> str:
    return f"p{page_number}_l{line_index}"


def _word_id(page_number: int, line_index: int, word_index: int) -> str:
    return f"p{page_number}_l{line_index}_w{word_index}"


def build_parser_layout_context(
    *,
    pages: tuple[OcrPage, ...] | list[OcrPage] | None,
    language: str,
    warnings: list[str] | tuple[str, ...] | None = None,
    config: ParserLayoutConfig | None = None,
    page_sizes: dict[int, tuple[int, int]] | None = None,
) -> BuiltParserContext:
    """Build deterministic layout context and an evidence ID index."""
    cfg = config or ParserLayoutConfig()
    page_list = list(pages or ())
    evidence_index: dict[str, dict[str, Any]] = {}
    out_pages: list[dict[str, Any]] = []
    total_lines = 0
    total_words = 0
    truncated = False

    if not cfg.enabled:
        payload = {
            "document": {"language": language, "page_count": len(page_list), "layout_enabled": False},
            "pages": [],
            "warnings": list(warnings or ()),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return BuiltParserContext(
            payload=payload,
            evidence_index={},
            context_chars=len(encoded),
            line_count=0,
            word_count=0,
            truncated=False,
        )

    for page in page_list:
        page_number = int(page.page)
        lines_out: list[dict[str, Any]] = []
        source_lines = list(page.lines) if page.lines else []
        if not source_lines and page.text.strip():
            # Fallback synthetic line when only page text exists (legacy OCR payloads).
            source_lines = [
                OcrLine(text=page.text.strip(), confidence=page.confidence, bbox=None, words=())
            ]

        for line_index, line in enumerate(source_lines, start=1):
            if total_lines >= cfg.max_lines:
                truncated = True
                break
            text = (line.text or "").strip()
            if not text:
                continue
            lid = _line_id(page_number, line_index)
            line_bbox = _bbox_list(line.bbox)
            line_entry: dict[str, Any] = {
                "id": lid,
                "text": text,
                "confidence": line.confidence,
                "bbox": line_bbox,
            }
            evidence_index[lid] = {
                "type": "line",
                "page": page_number,
                "text": text,
                "confidence": line.confidence,
                "bbox": line_bbox,
            }

            words_out: list[dict[str, Any]] = []
            if cfg.include_words:
                for word_index, word in enumerate(line.words or (), start=1):
                    if total_words >= cfg.max_words:
                        truncated = True
                        break
                    wtext = (word.text or "").strip()
                    if not wtext:
                        continue
                    wconf = word.confidence
                    if wconf is not None and wconf < cfg.min_word_confidence:
                        continue
                    wid = _word_id(page_number, line_index, word_index)
                    wbbox = _bbox_list(word.bbox)
                    word_entry = {
                        "id": wid,
                        "text": wtext,
                        "confidence": wconf,
                        "bbox": wbbox,
                        "block_number": word.block_number,
                        "paragraph_number": word.paragraph_number,
                        "line_number": word.line_number,
                        "word_number": word.word_number,
                    }
                    words_out.append(word_entry)
                    evidence_index[wid] = {
                        "type": "word",
                        "page": page_number,
                        "text": wtext,
                        "confidence": wconf,
                        "bbox": wbbox,
                        "line_id": lid,
                    }
                    total_words += 1
                if words_out:
                    line_entry["words"] = words_out

            lines_out.append(line_entry)
            total_lines += 1

        size = None
        if page_sizes and page_number in page_sizes:
            w, h = page_sizes[page_number]
            size = {"width": int(w), "height": int(h)}
        page_entry: dict[str, Any] = {"page": page_number, "lines": lines_out}
        if size:
            page_entry["size"] = size
        out_pages.append(page_entry)
        if truncated:
            break

    payload: dict[str, Any] = {
        "document": {
            "language": language,
            "page_count": len(out_pages),
            "layout_enabled": True,
            "truncated": truncated,
        },
        "pages": out_pages,
        "warnings": list(warnings or ()),
    }

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > cfg.max_context_chars:
        truncated = True
        # Truncate by dropping trailing pages/lines until under budget.
        while out_pages and len(encoded) > cfg.max_context_chars:
            last = out_pages[-1]
            lines = last.get("lines") or []
            if lines:
                removed = lines.pop()
                rid = removed.get("id")
                if isinstance(rid, str):
                    evidence_index.pop(rid, None)
                for word in removed.get("words") or []:
                    wid = word.get("id")
                    if isinstance(wid, str):
                        evidence_index.pop(wid, None)
                total_lines = max(0, total_lines - 1)
            else:
                out_pages.pop()
            payload["pages"] = out_pages
            payload["document"]["truncated"] = True
            payload["document"]["page_count"] = len(out_pages)
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    logger.debug(
        "payslip_parser_layout_context pages=%s lines=%s words=%s chars=%s truncated=%s",
        len(out_pages),
        total_lines,
        total_words,
        len(encoded),
        truncated,
    )
    return BuiltParserContext(
        payload=payload,
        evidence_index=evidence_index,
        context_chars=len(encoded),
        line_count=total_lines,
        word_count=total_words,
        truncated=truncated,
    )


def build_parser_layout_context_from_ocr_result(
    result: OCRResult,
    *,
    config: ParserLayoutConfig | None = None,
) -> BuiltParserContext:
    language = result.language_effective or result.language_requested or "auto"
    return build_parser_layout_context(
        pages=result.pages,
        language=language,
        warnings=list(result.warnings),
        config=config,
    )
