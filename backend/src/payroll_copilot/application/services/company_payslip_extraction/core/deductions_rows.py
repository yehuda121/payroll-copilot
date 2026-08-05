"""
Deterministic parser for statutory deduction rows.

Field catalogs come from the active company profile. The algorithm is generic:
same-row label/amount pairing, first match wins, percent tokens are rates.
"""

from __future__ import annotations

from payroll_copilot.application.services.company_payslip_extraction.core.layout import FieldCandidate, VisualRow, bbox_from_words
from payroll_copilot.application.services.company_payslip_extraction.core.profile import get_profile
from payroll_copilot.application.services.company_payslip_extraction.core.section_geometry import (
    is_percent_token,
    label_groups,
    label_variants,
    money_left_of,
)


def extract_deduction_fields(rows: list[VisualRow]) -> list[FieldCandidate]:
    """Same-row label/amount pairs for the statutory deductions."""
    profile = get_profile()
    field_names = profile.deduction_field_names
    row_labels = profile.deduction_row_labels
    found: dict[str, FieldCandidate] = {}
    seen_rows: set[str] = set()

    for row in rows:
        words = sorted(row.words, key=lambda w: w.x0)
        if not words:
            continue
        for start, end in label_groups(words, allow_percent=True):
            group = words[start : end + 1]
            text_tokens = [w.text for w in group if not is_percent_token(w.text)]
            row_label = next(
                (n for n in row_labels if n in label_variants(text_tokens)),
                None,
            )
            if row_label is None or row_label in seen_rows:
                continue
            seen_rows.add(row_label)

            amount_field, rate_field = row_labels[row_label]
            rate = next((w for w in group if is_percent_token(w.text)), None)
            if rate_field and rate is not None and rate_field not in found:
                found[rate_field] = FieldCandidate(
                    name=rate_field,
                    value=rate.text,
                    raw=" ".join(w.text for w in group),
                    bbox=bbox_from_words(row.page, group),
                    confidence="high",
                    status="ok",
                )

            money = money_left_of(words, start)
            if money is None or amount_field in found:
                continue
            pair = [money, *group]
            found[amount_field] = FieldCandidate(
                name=amount_field,
                value=money.text,
                raw=" ".join(w.text for w in pair),
                bbox=bbox_from_words(row.page, pair),
                confidence="high",
                status="ok",
            )

    return [found[n] for n in field_names if n in found]
