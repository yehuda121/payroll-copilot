"""
Relative-geometry primitives for colon-less label/value rows.

Payslip summary and deduction lines print the label as a right-to-left Hebrew
phrase with its amount in the column immediately to the *left*. There is no
colon to anchor on, so these rows are read by grouping tokens and following the
same RTL value-left-of-label convention used elsewhere in the parser.

Everything here is derived from the row's own token spacing — no absolute page
coordinates and no per-document constants.
"""

from __future__ import annotations

import re
from typing import Sequence

from payroll_copilot.application.services.company_payslip_extraction.core.hebrew import normalize_hebrew_label, unreverse_hebrew_runs
from payroll_copilot.application.services.company_payslip_extraction.core.layout import WordSpan

# Monetary amounts are always printed with exactly two decimals. Requiring them
# keeps IDs, years, employee numbers and bare integers out of the value slot.
MONEY_TOKEN = re.compile(r"(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}")
PERCENT_TOKEN = re.compile(r"\d{1,3}(?:\.\d+)?%")

# A label never contains digits, so a numeric token always ends a label group
_LABEL_SPLIT_RATIO = 1.5
_VALUE_GAP_HEIGHT_RATIO = 12.0


def is_money_token(text: str) -> bool:
    return bool(MONEY_TOKEN.fullmatch((text or "").strip()))


def is_percent_token(text: str) -> bool:
    return bool(PERCENT_TOKEN.fullmatch((text or "").strip()))


def _median(values: Sequence[float], default: float) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else default


def row_median_gap(words: Sequence[WordSpan]) -> float:
    return _median([b.x0 - a.x1 for a, b in zip(words, words[1:]) if b.x0 - a.x1 > 0], 4.0)


def row_median_height(words: Sequence[WordSpan]) -> float:
    return _median([w.bottom - w.top for w in words], 8.0)


def logical_label(tokens: Sequence[str]) -> str:
    """Turn visually-ordered RTL tokens into a logical Hebrew phrase."""
    parts = [unreverse_hebrew_runs(t) for t in tokens if t]
    return " ".join(reversed(parts)).strip()


def label_variants(tokens: Sequence[str]) -> set[str]:
    """All readings of a label group that a target name may legitimately match."""
    joined = " ".join(t for t in tokens if t).strip()
    if not joined:
        return set()
    return {joined, normalize_hebrew_label(joined), logical_label(tokens)}


def label_groups(
    words: Sequence[WordSpan],
    *,
    allow_percent: bool = False,
) -> list[tuple[int, int]]:
    """
    Inclusive ``(start, end)`` index ranges of contiguous label tokens.

    Numeric tokens end a group, and so does a horizontal gap noticeably wider
    than the row's own median gap — that is what separates neighbouring column
    labels printed on the same visual line.
    """
    if not words:
        return []
    split_gap = max(row_median_gap(words) * _LABEL_SPLIT_RATIO, 8.0)

    def is_label_token(w: WordSpan) -> bool:
        text = (w.text or "").strip()
        if not text:
            return False
        if allow_percent and is_percent_token(text):
            return True
        return not any(c.isdigit() for c in text)

    groups: list[tuple[int, int]] = []
    start: int | None = None
    for i, w in enumerate(words):
        if not is_label_token(w):
            if start is not None:
                groups.append((start, i - 1))
                start = None
            continue
        if start is None:
            start = i
        elif w.x0 - words[i - 1].x1 > split_gap:
            groups.append((start, i - 1))
            start = i
    if start is not None:
        groups.append((start, len(words) - 1))
    return groups


def money_left_of(words: Sequence[WordSpan], start: int) -> WordSpan | None:
    """
    The amount that belongs to a label group starting at ``start``.

    It must be the token immediately to the left on the same visual row, so a
    number sitting in another column (or behind another label) is never used.
    """
    idx = start - 1
    if idx < 0:
        return None
    candidate = words[idx]
    if not is_money_token(candidate.text):
        return None
    gap = words[start].x0 - candidate.x1
    if gap < 0:
        return None
    if gap > row_median_height(words) * _VALUE_GAP_HEIGHT_RATIO:
        return None
    return candidate
