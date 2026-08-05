"""Line-based field parsing (fallback) and re-exports of Hebrew helpers."""

from __future__ import annotations

from typing import Any, Optional

from payroll_copilot.application.services.company_payslip_extraction.core.hebrew import (
    is_label_like,
    is_value_like,
    normalize_hebrew_label,
)
from payroll_copilot.application.services.company_payslip_extraction.core.layout import (
    FieldCandidate,
    entries_to_fields_map,
    extract_payslip_header_dates,
    merge_header_date_candidates,
    refine_field_candidates,
    segment_row_fields,
)


def parse_colon_line(line: str) -> dict[str, str]:
    """Single-colon line parse (normal or RTL-reversed). Preserves ``raw``."""
    raw = line.strip()
    before, after = raw.split(":", 1)
    before, after = before.strip(), after.strip()

    reversed_layout = False
    if not before and is_label_like(after):
        reversed_layout = True
    elif is_value_like(before) and is_label_like(after):
        reversed_layout = True
    elif is_label_like(after) and not is_label_like(before):
        reversed_layout = True

    if reversed_layout:
        name = normalize_hebrew_label(after)
        value = before
    else:
        name = normalize_hebrew_label(before) if is_label_like(before) else before
        value = after

    return {"name": name.strip(), "value": value.strip(), "raw": raw}


def _candidate_to_entry(c: FieldCandidate) -> dict[str, Any]:
    return {
        "name": c.name,
        "value": c.value,
        "raw": c.raw,
        "bbox": c.bbox,
        "confidence": c.confidence,
        "status": c.status,
    }


def _segment_plain_text(text: str) -> list[FieldCandidate]:
    """Run multi-field segmentation on plain text without coordinates."""

    class _TextRow:
        page = 0
        y = 0.0
        words: list = []

        @property
        def text(self) -> str:
            return text

        @property
        def bbox(self):
            return None

    return segment_row_fields(_TextRow())  # type: ignore[arg-type]


def parse_payslip_lines(lines: list[str]) -> list[dict[str, Any]]:
    """
    Fallback line parser. Multi-colon lines use the shared segmenter.
    Results are refined (helpers merged, footers demoted) before return.
    """
    cands: list[FieldCandidate] = []

    for raw_line in lines:
        line = (raw_line or "").strip()
        if not line:
            continue

        if ":" in line:
            cands.extend(_segment_plain_text(line))
        else:
            cands.append(
                FieldCandidate(
                    name="",
                    value=line,
                    raw=line,
                    bbox=None,
                    confidence="unknown",
                    status="unclassified",
                )
            )

    refined = refine_field_candidates(cands)
    merged = merge_header_date_candidates(
        refined, extract_payslip_header_dates(lines=lines)
    )
    return [_candidate_to_entry(c) for c in merged]


def parse_paystub_fields(lines: list[str]) -> dict[str, str]:
    return entries_to_fields_map(parse_payslip_lines(lines))


def parse_fields(raw_text: str) -> dict[str, str]:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    return parse_paystub_fields(lines)


def get_field(fields: dict[str, str], key: str) -> Optional[str]:
    return fields.get(key)
