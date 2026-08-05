"""Deterministic Israeli ID card field parser."""

from __future__ import annotations

from payroll_copilot.application.services.deterministic_pdf.parsers._common import (
    field,
    find_date,
    find_israeli_id,
    first_label_value,
    page_of,
)
from payroll_copilot.application.services.deterministic_pdf.types import NormalizedExtractedField
from payroll_copilot.application.services.employee_fixed_document_extractor import (
    ground_id_card_values,
)

_NAME_LABELS = (
    r"full\s*name",
    r"name",
    r"שם\s*מלא",
    r"שם\s*הנושא",
    r"שם",
)
_BIRTH_LABELS = (
    r"date\s*of\s*birth",
    r"birth\s*date",
    r"תאריך\s*לידה",
    r"נולד(?:ה)?\s*ב",
)


def parse_national_id_text(
    raw_text: str,
    *,
    page_texts: list[str] | tuple[str, ...] | None = None,
) -> list[NormalizedExtractedField]:
    text = raw_text or ""
    pages = tuple(page_texts or ((text,) if text else ()))

    name, name_line = first_label_value(text, _NAME_LABELS)
    nid, nid_line = find_israeli_id(text)
    birth, birth_line = find_date(text, _BIRTH_LABELS)

    grounded = ground_id_card_values(
        full_name=name or "",
        national_id=nid or "",
        birth_date=birth or "",
        ocr_text=text,
    )

    out: list[NormalizedExtractedField] = []
    for key, value, line in (
        ("full_name", grounded.get("full_name"), name_line),
        ("national_id", grounded.get("national_id"), nid_line),
        ("birth_date", grounded.get("birth_date"), birth_line),
    ):
        item = field(key, value or None, source_text=line, page=page_of(text, pages, line))
        if item is not None:
            out.append(item)
    return out
