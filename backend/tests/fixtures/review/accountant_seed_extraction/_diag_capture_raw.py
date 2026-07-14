"""One-off diagnosis helper: capture raw Ollama response + semantic reject category.

Does not write DB / seed. Safe to delete after review.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from payroll_copilot.application.exceptions import PayslipParserSemanticError
from payroll_copilot.application.services.parser_semantic import (
    normalize_payslip_parser_payload,
    validate_payslip_parser_payload,
)
from payroll_copilot.application.services.parser_layout_context import (
    ParserLayoutConfig,
    build_parser_layout_context,
)
from payroll_copilot.application.ports.ocr import OcrLine, OcrPage, OcrWord
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import OllamaPayslipParser
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.config.ollama_resolver import get_resolved_ollama_base_url


def pages_from_ocr(payload: dict) -> tuple[OcrPage, ...]:
    pages = []
    for page in payload.get("pages") or []:
        lines = []
        for line in page.get("lines") or []:
            words = []
            for w in line.get("words") or []:
                bbox = w.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                words.append(
                    OcrWord(
                        text=w.get("text") or "",
                        confidence=w.get("confidence"),
                        bbox=tuple(float(x) for x in bbox),
                        block_number=int(w.get("block_number") or 0),
                        paragraph_number=int(w.get("paragraph_number") or 0),
                        line_number=int(w.get("line_number") or 0),
                        word_number=int(w.get("word_number") or 0),
                    )
                )
            lines.append(
                OcrLine(
                    text=line.get("text") or "",
                    confidence=line.get("confidence"),
                    bbox=tuple(line["bbox"]) if line.get("bbox") and len(line["bbox"]) == 4 else None,
                    words=tuple(words),
                )
            )
        page_words = []
        for w in page.get("words") or []:
            bbox = w.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            page_words.append(
                OcrWord(
                    text=w.get("text") or "",
                    confidence=w.get("confidence"),
                    bbox=tuple(float(x) for x in bbox),
                    block_number=int(w.get("block_number") or 0),
                    paragraph_number=int(w.get("paragraph_number") or 0),
                    line_number=int(w.get("line_number") or 0),
                    word_number=int(w.get("word_number") or 0),
                )
            )
        pages.append(
            OcrPage(
                page=int(page.get("page") or 1),
                language=page.get("language") or "auto",
                text=page.get("text") or "",
                confidence=page.get("confidence"),
                lines=tuple(lines),
                words=tuple(page_words),
            )
        )
    return tuple(pages)


async def main() -> None:
    ocr_path = Path(__file__).with_name("_diag_ocr.json")
    out_path = Path(__file__).with_name("_diag_raw_model.json")
    payload = json.loads(ocr_path.read_text(encoding="utf-8"))
    settings = get_settings()
    model = settings.payslip_parser_model or settings.ollama_default_model
    base_url = get_resolved_ollama_base_url(settings)
    parser = OllamaPayslipParser(
        base_url=base_url,
        model=model,
        timeout_seconds=float(settings.payslip_parser_timeout_seconds),
        temperature=float(settings.payslip_parser_temperature),
        use_json_format=bool(settings.payslip_parser_use_json_format),
        layout_enabled=bool(settings.payslip_parser_layout_enabled),
    )
    pages = pages_from_ocr(payload)
    lang = payload.get("language_effective") or payload.get("language") or "heb+eng"
    layout = build_parser_layout_context(
        pages=pages,
        language=lang,
        warnings=list(payload.get("warnings") or []),
        config=ParserLayoutConfig(enabled=True, include_words=True),
    )
    user_content = parser._build_user_prompt(
        ocr_text=payload.get("raw_text") or "",
        language=lang,
        pages_text=[p.text for p in pages] if pages else None,
        layout_context=layout.payload if layout.payload else None,
        retry_hint=None,
    )
    print("SETTINGS model=", model, "base=", base_url)
    print("PROMPT_CHARS", len(user_content))
    print("LAYOUT_LINES", layout.line_count, "WORDS", layout.word_count, "CTX", layout.context_chars)
    raw_content, model_name = await parser._chat(user_content)
    result = {
        "model": model_name,
        "raw_model_response": raw_content,
        "raw_len": len(raw_content),
    }
    try:
        from payroll_copilot.infrastructure.ai.payslip_parser_ollama import _parse_json_object

        parsed = _parse_json_object(raw_content)
        parsed, norm_warnings = normalize_payslip_parser_payload(parsed)
        result["normalize_warnings"] = norm_warnings
        result["parsed_top_keys"] = sorted(parsed.keys())
        # summarize field statuses
        statuses = {}
        for k, v in parsed.items():
            if isinstance(v, dict) and "status" in v:
                statuses[k] = {
                    "status": v.get("status"),
                    "value": v.get("value"),
                    "evidence_ids": v.get("evidence_ids"),
                    "keys": sorted(v.keys()),
                }
        result["field_summary"] = statuses
        validate_payslip_parser_payload(
            parsed,
            ocr_text=payload.get("raw_text") or "",
            layout_context=layout.payload if isinstance(layout.payload, dict) else None,
        )
        result["semantic"] = "accepted"
    except PayslipParserSemanticError as exc:
        result["semantic"] = "rejected"
        result["category"] = exc.category
        result["warning_code"] = exc.warning_code
        result["message"] = exc.message
    except Exception as exc:  # noqa: BLE001
        result["semantic"] = "error"
        result["error_type"] = type(exc).__name__
        result["message"] = str(exc)

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", out_path)
    print("semantic", result.get("semantic"), result.get("category"), result.get("warning_code"))
    print("raw_preview", raw_content[:1200])


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
