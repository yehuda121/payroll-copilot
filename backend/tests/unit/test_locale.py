"""Unit tests for locale resolution."""

from __future__ import annotations

from payroll_copilot.infrastructure.i18n import normalize_locale, resolve_locale


def test_normalize_locale_supported_codes() -> None:
    assert normalize_locale("he") == "he"
    assert normalize_locale("en") == "en"
    assert normalize_locale("ar") == "ar"


def test_normalize_locale_region_and_case() -> None:
    assert normalize_locale("HE-IL") == "he"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("ar_SA") == "ar"


def test_normalize_locale_unknown_falls_back_to_default() -> None:
    assert normalize_locale("fr", default="he") == "he"
    assert normalize_locale(None, default="en") == "en"


def test_resolve_prefers_explicit_over_accept_language() -> None:
    assert (
        resolve_locale(explicit="ar", accept_language="en-US,en;q=0.9", default="he") == "ar"
    )


def test_resolve_uses_accept_language_when_explicit_missing() -> None:
    assert resolve_locale(explicit=None, accept_language="en-US,en;q=0.8", default="he") == "en"


def test_resolve_falls_back_to_default() -> None:
    assert resolve_locale(explicit=None, accept_language=None, default="he") == "he"
