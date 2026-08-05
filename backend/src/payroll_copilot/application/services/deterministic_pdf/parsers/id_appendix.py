"""Deterministic ID appendix (children) field parser."""

from __future__ import annotations

import re

from payroll_copilot.application.services.deterministic_pdf.parsers._common import (
    field,
    find_israeli_id,
    first_label_value,
)
from payroll_copilot.application.services.deterministic_pdf.types import NormalizedExtractedField
from payroll_copilot.application.services.employee_document_form_schemas import normalize_children_list

_CHILD_BLOCK_RE = re.compile(
    r"(?im)(?:child|ילדים|ילד|ילדה)\s*[:\-]?\s*(.+)$"
)
_NAME_ID_RE = re.compile(
    r"(?P<name>[A-Za-z\u0590-\u05FF][A-Za-z\u0590-\u05FF\s'\-]{1,80}?)"
    r"(?:\s+|,)\s*(?P<id>\d{8,9})"
)


def parse_id_appendix_text(
    raw_text: str,
    *,
    page_texts: list[str] | tuple[str, ...] | None = None,
) -> list[NormalizedExtractedField]:
    _ = page_texts
    text = raw_text or ""
    children: list[dict[str, str]] = []

    for match in _CHILD_BLOCK_RE.finditer(text):
        line = match.group(1).strip()
        pair = _NAME_ID_RE.search(line)
        if pair:
            children.append(
                {
                    "full_name": pair.group("name").strip(),
                    "national_id": pair.group("id").zfill(9),
                }
            )
            continue
        nid, _ = find_israeli_id(line)
        name, _ = first_label_value(line, (r"name", r"שם"))
        if name or nid:
            children.append(
                {
                    "full_name": (name or "").strip(),
                    "national_id": (nid or "").zfill(9) if nid else "",
                }
            )

    # Also scan whole text for name+id pairs under a children section.
    if not children:
        for pair in _NAME_ID_RE.finditer(text):
            children.append(
                {
                    "full_name": pair.group("name").strip(),
                    "national_id": pair.group("id").zfill(9),
                }
            )

    normalized = normalize_children_list(children)
    item = field("children", normalized if normalized else None, source_text=None, confidence=0.85)
    return [item] if item is not None else []
