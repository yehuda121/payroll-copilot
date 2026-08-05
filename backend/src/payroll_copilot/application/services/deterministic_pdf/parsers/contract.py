"""Deterministic employment contract field parser."""

from __future__ import annotations

from payroll_copilot.application.services.deterministic_pdf.parsers._common import (
    field,
    find_date,
    first_label_value,
    first_money_after_labels,
    page_of,
)
from payroll_copilot.application.services.deterministic_pdf.types import NormalizedExtractedField

_COMMENCEMENT_LABELS = (
    r"employment\s*(?:commencement|start)\s*date",
    r"start\s*date",
    r"תחילת\s*עבודה",
    r"מועד\s*תחילת\s*העסקה",
    r"תאריך\s*תחילת\s*עבודה",
)
_BASIS_LABELS = (
    r"salary\s*basis",
    r"compensation\s*basis",
    r"בסיס\s*שכר",
    r"שיטת\s*תשלום",
)
_MONTHLY_LABELS = (
    r"monthly\s*salary",
    r"contractual\s*monthly",
    r"שכר\s*חודשי",
    r"משכורת\s*חודשית",
)
_HOURLY_LABELS = (r"hourly\s*rate", r"contractual\s*hourly", r"שכר\s*שעתי", r"תעריף\s*שעתי")
_DAILY_LABELS = (r"daily\s*rate", r"contractual\s*daily", r"שכר\s*יומי", r"תעריף\s*יומי")
_EFFECTIVE_FROM = (r"effective\s*from", r"בתוקף\s*מ", r"תחילת\s*תוקף")
_EFFECTIVE_TO = (r"effective\s*to", r"בתוקף\s*עד", r"סיום\s*תוקף")


def parse_contract_text(
    raw_text: str,
    *,
    page_texts: list[str] | tuple[str, ...] | None = None,
) -> list[NormalizedExtractedField]:
    text = raw_text or ""
    pages = tuple(page_texts or ((text,) if text else ()))
    out: list[NormalizedExtractedField] = []

    def add(item: NormalizedExtractedField | None) -> None:
        if item is not None:
            out.append(item)

    commencement, line = find_date(text, _COMMENCEMENT_LABELS)
    add(
        field(
            "employment_commencement_date",
            commencement,
            source_text=line,
            page=page_of(text, pages, line),
        )
    )

    basis, basis_line = first_label_value(text, _BASIS_LABELS)
    if basis:
        lowered = basis.lower()
        if "hour" in lowered or "שעת" in basis:
            basis = "hourly"
        elif "day" in lowered or "יום" in basis:
            basis = "daily"
        elif "month" in lowered or "חודש" in basis:
            basis = "monthly"
    add(field("salary_basis", basis, source_text=basis_line, page=page_of(text, pages, basis_line)))

    for key, labels in (
        ("contractual_monthly_salary", _MONTHLY_LABELS),
        ("contractual_hourly_rate", _HOURLY_LABELS),
        ("contractual_daily_rate", _DAILY_LABELS),
    ):
        value, money_line = first_money_after_labels(text, labels)
        add(field(key, value, source_text=money_line, page=page_of(text, pages, money_line)))

    eff_from, from_line = find_date(text, _EFFECTIVE_FROM)
    add(field("effective_from", eff_from, source_text=from_line, page=page_of(text, pages, from_line)))
    eff_to, to_line = find_date(text, _EFFECTIVE_TO)
    add(field("effective_to", eff_to, source_text=to_line, page=page_of(text, pages, to_line)))

    return out
