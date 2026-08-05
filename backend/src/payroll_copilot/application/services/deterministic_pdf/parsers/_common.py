"""Shared regex helpers for deterministic field parsing."""

from __future__ import annotations

import re
from typing import Any

from payroll_copilot.application.services.deterministic_pdf.types import NormalizedExtractedField
from payroll_copilot.application.services.employee_fixed_document_extractor import is_valid_israeli_id

_MONEY_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?!\d)"
)
_ID_CANDIDATE_RE = re.compile(r"\b(\d{8,9})\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}[./\-]\d{1,2}[./\-]\d{1,2})\b"
)
_PERIOD_RE = re.compile(
    r"(?:(?:pay\s*period|period|חודש|תקופת\s*שכר|עבור\s*חודש)\s*[:\-]?\s*)?"
    r"((?:0?[1-9]|1[0-2])[/\-.](?:20\d{2})|(?:20\d{2})[/\-.](?:0?[1-9]|1[0-2])|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})",
    re.IGNORECASE,
)


def first_label_value(text: str, labels: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Return (value, matched_line) for the first label: value pattern."""
    for label in labels:
        pattern = re.compile(
            rf"(?im)^[^\n]*?(?:{label})\s*[:\-–]?\s*(.+)$"
        )
        match = pattern.search(text)
        if not match:
            continue
        value = match.group(1).strip()
        value = re.split(r"\s{2,}|\t", value)[0].strip()
        value = value.strip(" |;")
        if value:
            return value, match.group(0).strip()
    return None, None


def first_money_after_labels(text: str, labels: tuple[str, ...]) -> tuple[str | None, str | None]:
    value, line = first_label_value(text, labels)
    if value is None:
        return None, None
    money = _MONEY_RE.search(value.replace(",", ""))
    if money:
        return money.group(1).replace(" ", "").replace(",", ""), line
    money = _MONEY_RE.search(line or "")
    if money:
        return money.group(1).replace(" ", "").replace(",", ""), line
    return None, line


def find_israeli_id(text: str) -> tuple[str | None, str | None]:
    for match in _ID_CANDIDATE_RE.finditer(text):
        candidate = match.group(1)
        if is_valid_israeli_id(candidate):
            # Prefer line containing the match as source_text.
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end < 0:
                line_end = len(text)
            return candidate.zfill(9), text[line_start:line_end].strip()
    return None, None


def find_date(text: str, labels: tuple[str, ...] = ()) -> tuple[str | None, str | None]:
    if labels:
        value, line = first_label_value(text, labels)
        if value:
            date_match = _DATE_RE.search(value) or _DATE_RE.search(line or "")
            if date_match:
                return date_match.group(1), line
    match = _DATE_RE.search(text)
    if match:
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        return match.group(1), text[line_start:line_end].strip()
    return None, None


def find_pay_period(text: str) -> tuple[str | None, str | None]:
    match = _PERIOD_RE.search(text)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(0).strip()


def field(
    key: str,
    value: Any,
    *,
    source_text: str | None = None,
    page: int | None = None,
    confidence: float = 0.9,
) -> NormalizedExtractedField | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return NormalizedExtractedField(
        key=key,
        value=value.strip() if isinstance(value, str) else value,
        confidence=confidence,
        source_text=source_text,
        page=page,
        status="FOUND",
    )


def page_of(text: str, page_texts: list[str] | tuple[str, ...], needle: str | None) -> int | None:
    if not needle:
        return None
    for index, page in enumerate(page_texts, start=1):
        if needle in page:
            return index
    return 1 if page_texts else None
