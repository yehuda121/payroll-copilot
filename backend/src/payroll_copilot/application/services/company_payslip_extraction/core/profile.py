"""Active company profile for the duration of one extraction (or test)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class CompanyProfile:
    """Configuration + thin hooks for one payslip format. No extraction engine."""

    key: str
    start_markers: tuple[str, ...]
    end_markers: tuple[str, ...]
    title_markers: tuple[str, ...]
    logical_label_hints: tuple[str, ...]
    visual_label_hints: tuple[str, ...]
    label_aliases: dict[str, str]
    apostrophe_label_allow: frozenset[str]
    yes_no_value_aliases: dict[str, str]
    employment_type_tokens: dict[str, str]
    name_reject_substrings: tuple[str, ...]
    footer_label_hints: tuple[str, ...]
    footer_label_exceptions: frozenset[str]
    structural_label_bigrams: frozenset[tuple[str, str]]
    incomplete_standalone_labels: frozenset[str]
    extendable_partial_labels: frozenset[str]
    complete_short_labels: frozenset[str]
    helper_labels: frozenset[str]
    summary_field_names: tuple[str, ...]
    deduction_field_names: tuple[str, ...]
    # printed row label → (amount field, optional rate field)
    deduction_row_labels: dict[str, tuple[str, str | None]]
    employment_scope_label: str = "היקף משרה"


_active: ContextVar[CompanyProfile | None] = ContextVar(
    "payslip_company_profile", default=None
)


def get_profile() -> CompanyProfile:
    profile = _active.get()
    if profile is None:
        raise RuntimeError(
            "No company profile is active. Call extract via the registry "
            "or activate_profile(...) before using core helpers."
        )
    return profile


def get_profile_or_none() -> CompanyProfile | None:
    return _active.get()


def activate_profile(profile: CompanyProfile) -> None:
    """Set the active profile for the current context (tests / long-lived callers)."""
    _active.set(profile)


@contextmanager
def use_profile(profile: CompanyProfile) -> Iterator[CompanyProfile]:
    token = _active.set(profile)
    try:
        yield profile
    finally:
        _active.reset(token)
