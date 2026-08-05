"""Deterministic payslip extraction engine — company-agnostic orchestration."""

from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from typing import Any, Callable

import pdfplumber

from payroll_copilot.application.services.company_payslip_extraction.core.deductions_rows import extract_deduction_fields
from payroll_copilot.application.services.company_payslip_extraction.core.layout import (
    LayoutTemplate,
    build_visual_rows,
    candidates_to_entries,
    collect_cross_payslip_repeats,
    collect_repeatable_labels,
    entries_to_fields_map,
    extract_payslip_header_dates,
    extract_words,
    group_rows_into_payslips,
    learn_from_payslip,
    merge_additive_candidates,
    parse_rows_to_candidates,
    resolve_employee_names,
    words_usable,
)
from payroll_copilot.application.services.company_payslip_extraction.core.parser import parse_payslip_lines
from payroll_copilot.application.services.company_payslip_extraction.core.profile import CompanyProfile, use_profile
from payroll_copilot.application.services.company_payslip_extraction.core.summary_rows import extract_summary_fields

_ARTIFACT_MAP = str.maketrans({
    "\ufeff": "",
    "\u200e": "",
    "\u200f": "",
    "\u202a": "",
    "\u202b": "",
    "\u202c": "",
    "\u202d": "",
    "\u202e": "",
    "\xa0": " ",
})
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_line(line: str) -> str:
    if not line:
        return ""
    text = unicodedata.normalize("NFKC", line)
    text = text.translate(_ARTIFACT_MAP)
    text = _CONTROL_RE.sub("", text)
    return text.strip()


def _contains_marker(line: str, markers: tuple[str, ...]) -> bool:
    return any(marker in line for marker in markers)


def _make_boundary_predicates(
    profile: CompanyProfile,
) -> tuple[Callable[[str], bool], Callable[[str], bool]]:
    start = profile.start_markers
    end = profile.end_markers

    def is_start(line: str) -> bool:
        return _contains_marker(line, start)

    def is_end(line: str) -> bool:
        return _contains_marker(line, end)

    return is_start, is_end


def split_payslips(
    lines: list[str],
    *,
    profile: CompanyProfile,
) -> list[list[str]]:
    """Split flattened lines into payslip sections (start → end inclusive)."""
    if not lines:
        return []

    is_start, is_end = _make_boundary_predicates(profile)
    payslips: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        if is_start(line):
            if current is not None and any(current):
                payslips.append(current)
            current = [line]
            continue
        if current is None:
            continue
        current.append(line)
        if is_end(line):
            payslips.append(current)
            current = None

    if current is not None and any(current):
        payslips.append(current)

    return [block for block in payslips if any(ln.strip() for ln in block)]


def _extract_page_text(page: pdfplumber.page.Page) -> str:
    text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    if text.strip():
        return text

    chars = page.chars
    if not chars:
        return ""

    sorted_chars = sorted(
        chars, key=lambda c: (-round(float(c["top"]), 0), float(c["x0"]))
    )
    lines: list[str] = []
    current_y: float | None = None
    current_line: list[tuple[float, str]] = []

    for ch in sorted_chars:
        y = round(float(ch["top"]), 0)
        if current_y is None:
            current_y = y
        if abs(y - current_y) > 3:
            current_line.sort(key=lambda t: t[0])
            lines.append("".join(t[1] for t in current_line))
            current_line = []
            current_y = y
        current_line.append((float(ch["x0"]), ch.get("text", "")))

    if current_line:
        current_line.sort(key=lambda t: t[0])
        lines.append("".join(t[1] for t in current_line))

    return "\n".join(lines)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    pages_text: list[str] = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_text(page)
            if page_text.strip():
                pages_text.append(page_text.strip())
    return "\n\n".join(pages_text).strip()


def _guess_employee_name(entries: list[dict[str, Any]]) -> str:
    name_keys = {"שם עובד", "שם העובד", "שם", "שם מלא"}
    for entry in entries:
        name = (entry.get("name") or "").strip()
        value = (entry.get("value") or "").strip()
        if name in name_keys and value:
            return value
    return ""


def build_payslip_from_lines(index: int, block_lines: list[str]) -> dict[str, Any]:
    entries = parse_payslip_lines(block_lines)
    return {
        "paystub_index": index,
        "employee_name": _guess_employee_name(entries),
        "fields": entries_to_fields_map(entries),
        "entries": entries,
    }


def _extract_layout_payslips(
    file_bytes: bytes,
    *,
    profile: CompanyProfile,
) -> list[dict[str, Any]] | None:
    words = extract_words(file_bytes)
    if not words_usable(words):
        return None

    is_start, is_end = _make_boundary_predicates(profile)
    rows = build_visual_rows(words)
    row_blocks = group_rows_into_payslips(rows, is_start, is_end)
    if not row_blocks:
        return None

    template = LayoutTemplate()
    draft: list[tuple[list, list]] = []
    for block in row_blocks:
        cands = parse_rows_to_candidates(block)
        learn_from_payslip(template, block, cands)
        draft.append((block, cands))

    reject_values = collect_cross_payslip_repeats([c for _, c in draft])
    column_bounds = template.column_boundaries()
    repeat_labels = collect_repeatable_labels([c for _, c in draft])

    paystubs: list[dict[str, Any]] = []
    for index, (block, _first_cands) in enumerate(draft, start=1):
        cands = parse_rows_to_candidates(
            block,
            column_bounds=column_bounds,
            repeat_labels=repeat_labels,
        )
        learn_from_payslip(template, block, cands)
        resolved = resolve_employee_names(
            template, block, cands, reject_values=reject_values
        )
        learn_from_payslip(template, block, resolved)
        resolved = merge_additive_candidates(
            resolved, extract_payslip_header_dates(block)
        )
        resolved = merge_additive_candidates(resolved, extract_summary_fields(block))
        resolved = merge_additive_candidates(resolved, extract_deduction_fields(block))
        entries = candidates_to_entries(resolved)
        paystubs.append(
            {
                "paystub_index": index,
                "employee_name": _guess_employee_name(entries),
                "fields": entries_to_fields_map(entries),
                "entries": entries,
            }
        )
    return paystubs


def extract_document(
    file_bytes: bytes,
    *,
    profile: CompanyProfile,
    debug_layout: bool = False,
) -> dict[str, Any]:
    """
    Extract PDF text and payslips for the given company profile.

    Prefer layout-aware extraction when word coordinates are usable;
    otherwise fall back to the line-based parser. Does not call or report
    any LLM enrichment.
    """
    with use_profile(profile):
        raw_text = extract_text_from_pdf(file_bytes)
        lines = [clean_line(ln) for ln in raw_text.splitlines() if clean_line(ln)]

        extraction_mode = "lines"
        diagnostics: dict[str, Any] = {}

        layout_stubs = None
        try:
            layout_stubs = _extract_layout_payslips(file_bytes, profile=profile)
        except Exception as exc:  # noqa: BLE001
            diagnostics["layout_error"] = str(exc)
            layout_stubs = None

        if layout_stubs and len(layout_stubs) >= 1:
            line_blocks = split_payslips(lines, profile=profile)
            if len(layout_stubs) >= max(len(line_blocks), 1):
                extraction_mode = "layout"
                paystubs = layout_stubs
            elif line_blocks:
                extraction_mode = "lines"
                paystubs = [
                    build_payslip_from_lines(i, block)
                    for i, block in enumerate(line_blocks, start=1)
                ]
                diagnostics["layout_slip_count"] = len(layout_stubs)
            else:
                extraction_mode = "layout"
                paystubs = layout_stubs
        else:
            line_blocks = split_payslips(lines, profile=profile)
            paystubs = [
                build_payslip_from_lines(i, block)
                for i, block in enumerate(line_blocks, start=1)
            ]
            if not layout_stubs:
                diagnostics["fallback_reason"] = "no_usable_word_coordinates"

        if debug_layout:
            diagnostics["debug_layout"] = True

        return {
            "raw_text": raw_text,
            "paystubs": paystubs,
            "extraction_mode": extraction_mode,
            "diagnostics": diagnostics,
            "company_key": profile.key,
        }
