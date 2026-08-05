"""
Deterministic parser for the payslip summary totals.

Field names come from the active company profile. The algorithm is generic:
match label and monetary value only on the same visual row, take the amount
immediately left of the label group.
"""

from __future__ import annotations

from payroll_copilot.application.services.company_payslip_extraction.core.layout import FieldCandidate, VisualRow, bbox_from_words
from payroll_copilot.application.services.company_payslip_extraction.core.profile import get_profile
from payroll_copilot.application.services.company_payslip_extraction.core.section_geometry import label_groups, label_variants, money_left_of


def extract_summary_fields(rows: list[VisualRow]) -> list[FieldCandidate]:
    """One candidate per summary field, in payslip order; ambiguous rows are skipped."""
    field_names = get_profile().summary_field_names
    found: dict[str, FieldCandidate] = {}

    for row in rows:
        if len(found) == len(field_names):
            break
        words = sorted(row.words, key=lambda w: w.x0)
        if not words:
            continue
        for start, end in label_groups(words, allow_percent=False):
            group = words[start : end + 1]
            variants = label_variants([w.text for w in group])
            name = next(
                (n for n in field_names if n in variants and n not in found),
                None,
            )
            if name is None:
                continue
            money = money_left_of(words, start)
            if money is None:
                continue
            pair = [money, *group]
            found[name] = FieldCandidate(
                name=name,
                value=money.text,
                raw=" ".join(w.text for w in pair),
                bbox=bbox_from_words(row.page, pair),
                confidence="high",
                status="ok",
            )

    return [found[n] for n in field_names if n in found]
