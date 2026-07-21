"""Presentation-safe field keys for API / UI contracts.

DocumentInstance may retain arbitrary slots internally. Keys that look like
implementation identifiers must never appear in StructuredPayslipParse
``additional_fields``, API field DTOs, or digital-form models.
"""

from __future__ import annotations

import re

from payroll_copilot.application.ports.payslip_parser import PAYSLIP_FIELD_KEYS

# Explicit allowlist extras historically used in additional_fields.
_ALLOWED_EXTRA_KEYS = frozenset({"national_id", "total_deductions"})

_UNSAFE_EXACT = frozenset({"unknown", "dynamic_entries"})

# slot_can arises from slot.id[:8] when slot.id == "slot_cand…"
_UNSAFE_SUBSTRINGS = (
    "slot_can",
    "_slot_",
    "slot_",
    "candidate_",
    "_cand_",
)

_LEADING_INTERNAL = re.compile(
    r"^(unknown|slot_|candidate_|cand_)(_|$)",
    re.IGNORECASE,
)


def is_presentation_safe_field_key(key: str | None) -> bool:
    """Return True when ``key`` may appear in API/UI payroll field lists."""
    if key is None:
        return False
    text = str(key).strip()
    if not text:
        return False
    if text in PAYSLIP_FIELD_KEYS or text in _ALLOWED_EXTRA_KEYS:
        return True
    lower = text.casefold()
    if lower in _UNSAFE_EXACT or lower.startswith("unknown_"):
        return False
    if _LEADING_INTERNAL.match(text):
        return False
    for fragment in _UNSAFE_SUBSTRINGS:
        if fragment in lower:
            return False
    # Reject pure machine ids (uuid-like / hex stubs) without letters from UI langs.
    if re.fullmatch(r"[0-9a-f_\-]{8,}", lower):
        return False
    return True


def filter_presentation_safe_additional(
    additional: dict[str, object] | None,
) -> dict[str, object]:
    """Drop unsafe keys from an additional_fields mapping (values untouched)."""
    if not isinstance(additional, dict):
        return {}
    return {
        str(key): value
        for key, value in additional.items()
        if is_presentation_safe_field_key(str(key))
    }
