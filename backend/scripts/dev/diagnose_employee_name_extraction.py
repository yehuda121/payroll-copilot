#!/usr/bin/env python3
"""Read-only employee_name stage diagnostic from persisted DocumentExtraction artifacts.

Does NOT change extraction, prompts, grounding, or validation.
Does NOT call the LLM.

Usage (from backend/ with PYTHONPATH=src):

  python scripts/dev/diagnose_employee_name_extraction.py --extraction-json path/to/extraction.json

Or pass individual fields via a dump that includes:
  raw_text, ocr_result, structured_data, layout_snapshot (optional)

Expected dump shape (any of):
  { "raw_text": "...", "structured_data": {...}, "ocr_result": {...} }
  { "extraction": { ... same fields ... } }

Prints a stage table and non-PII outcome categories only.
Never substitutes profile/DB names as document employee_name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data.get("extraction"), dict):
        return dict(data["extraction"])
    return data


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _field_value(structured: dict[str, Any], key: str) -> Any:
    raw = structured.get(key)
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _entries(structured: dict[str, Any]) -> list[dict[str, Any]]:
    entries = structured.get("dynamic_entries")
    if isinstance(entries, list):
        return [e for e in entries if isinstance(e, dict)]
    return []


def _name_candidates_from_ocr(ocr_result: dict[str, Any], raw_text: str) -> list[dict[str, str]]:
    """Heuristic: list OCR line candidates that look letter-bearing (non-PII truncated)."""
    out: list[dict[str, str]] = []
    pages = ocr_result.get("pages") if isinstance(ocr_result, dict) else None
    lines: list[str] = []
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_no = int(page.get("page") or 1)
            page_lines = page.get("lines") or []
            if page_lines:
                for idx, line in enumerate(page_lines):
                    text = ""
                    if isinstance(line, dict):
                        text = str(line.get("text") or "").strip()
                    else:
                        text = str(line or "").strip()
                    if text:
                        lines.append(f"ocr_p{page_no}_l{idx}|{text}")
            else:
                for idx, line_text in enumerate(str(page.get("text") or "").splitlines()):
                    t = line_text.strip()
                    if t:
                        lines.append(f"ocr_p{page_no}_t{idx}|{t}")
    if not lines and raw_text:
        for idx, line_text in enumerate(raw_text.splitlines()):
            t = line_text.strip()
            if t:
                lines.append(f"ocr_p1_t{idx}|{t}")
    letter = re.compile(r"[A-Za-z\u0590-\u05FF\u0600-\u06FF]")
    for row in lines:
        cid, _, text = row.partition("|")
        if not letter.search(text):
            continue
        # Skip obvious money/URL/caption-ish tokens without storing full PII beyond length.
        if any(tok in text for tok in ("http", "www.", "₪", "%")):
            continue
        out.append({"candidate_id": cid, "value_len": str(len(text)), "has_letters": "yes"})
    return out[:40]


def diagnose(payload: dict[str, Any]) -> dict[str, Any]:
    raw_text = _as_text(payload.get("raw_text"))
    ocr_result = payload.get("ocr_result") if isinstance(payload.get("ocr_result"), dict) else {}
    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    meta = structured.get("extractor_meta") if isinstance(structured.get("extractor_meta"), dict) else {}
    entries = _entries(structured)
    name_entry = next((e for e in entries if e.get("key") == "employee_name"), None)
    structured_name = _field_value(structured, "employee_name")
    outcome = meta.get("employee_name_outcome")
    warnings = [str(w) for w in (payload.get("warnings") or meta.get("warnings") or []) if w]
    candidates = _name_candidates_from_ocr(ocr_result, raw_text)

    stages = [
        {
            "stage": "raw_text_nonempty",
            "present": bool(raw_text.strip()),
            "evidence": f"len={len(raw_text)}",
        },
        {
            "stage": "ocr_result_pages",
            "present": bool(ocr_result.get("pages")),
            "evidence": f"pages={len(ocr_result.get('pages') or [])}",
        },
        {
            "stage": "letter_bearing_ocr_line_candidates",
            "present": bool(candidates),
            "evidence": f"count={len(candidates)} sample_ids={[c['candidate_id'] for c in candidates[:5]]}",
        },
        {
            "stage": "extractor_meta.employee_name_outcome",
            "present": outcome is not None,
            "evidence": str(outcome),
        },
        {
            "stage": "dynamic_entries.employee_name",
            "present": name_entry is not None and bool(str(name_entry.get("value") or "").strip()),
            "evidence": (
                f"status={name_entry.get('status')}" if name_entry else "missing_entry"
            ),
        },
        {
            "stage": "structured_data.employee_name",
            "present": structured_name not in (None, ""),
            "evidence": "present" if structured_name not in (None, "") else "missing",
        },
        {
            "stage": "grounding_reject_warnings",
            "present": any("employee_name_rejected" in w or "unsupported_model_value" in w for w in warnings),
            "evidence": [w for w in warnings if "employee_name" in w][:8],
        },
    ]

    first_broken = None
    if not raw_text.strip() and not ocr_result.get("pages"):
        first_broken = "OCR/raw_text"
    elif not candidates:
        first_broken = "evidence_candidates (no letter-bearing OCR lines)"
    elif outcome in {None, "employee_name_missing"} and not (
        name_entry and str(name_entry.get("value") or "").strip()
    ):
        # Cannot distinguish LLM vs grounding without persisted proposal — report honestly.
        first_broken = (
            "LLM_or_grounding (employee_name_outcome="
            f"{outcome!r}; proposal JSON not persisted — NOT PROVEN which)"
        )
    elif name_entry and not structured_name:
        first_broken = "structured_projection"
    else:
        first_broken = "none_detected_or_name_present"

    return {
        "employee_name_outcome": outcome,
        "evidence_candidate_count_meta": meta.get("evidence_candidate_count"),
        "grounded_canonical_count": meta.get("grounded_canonical_count"),
        "first_broken_stage_estimate": first_broken,
        "stages": stages,
        "notes": [
            "This tool never reads employee profile/DB names.",
            "Full OCR line text is not printed (privacy).",
            "LLM proposal evidence_ids are not available unless stored in extractor_meta.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extraction-json",
        type=Path,
        help="Path to a persisted extraction dump JSON",
    )
    args = parser.parse_args()
    if args.extraction_json is None:
        print(
            "NO_EXTRACTION_DUMP: pass --extraction-json <path>. "
            "Real DocumentExtraction records were not found as committed fixtures.",
            file=sys.stderr,
        )
        print(
            json.dumps(
                {
                    "status": "NOT_PROVEN",
                    "reason": "no_extraction_dump_provided",
                    "hint": (
                        "Export DocumentExtraction fields raw_text, ocr_result, "
                        "structured_data (incl. extractor_meta / dynamic_entries) "
                        "for the failing document_id, then re-run this script."
                    ),
                },
                indent=2,
            )
        )
        return 2
    if not args.extraction_json.exists():
        print(f"File not found: {args.extraction_json}", file=sys.stderr)
        return 2
    result = diagnose(_load(args.extraction_json))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
