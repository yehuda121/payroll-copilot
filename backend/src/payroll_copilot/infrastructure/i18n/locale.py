"""Locale resolution for API requests."""

from __future__ import annotations

from payroll_copilot.domain.enums import SupportedLocale

_SUPPORTED = {locale.value for locale in SupportedLocale}
_DEFAULT = SupportedLocale.HEBREW.value


def normalize_locale(value: str | None, *, default: str = _DEFAULT) -> str:
    """Return a supported locale code, falling back to default."""
    if value is None:
        return default if default in _SUPPORTED else SupportedLocale.HEBREW.value
    candidate = value.strip().lower().replace("_", "-")
    if not candidate:
        return default if default in _SUPPORTED else SupportedLocale.HEBREW.value
    primary = candidate.split(",", maxsplit=1)[0].split(";", maxsplit=1)[0].strip()
    if primary in _SUPPORTED:
        return primary
    if "-" in primary:
        short = primary.split("-", maxsplit=1)[0]
        if short in _SUPPORTED:
            return short
    return default if default in _SUPPORTED else SupportedLocale.HEBREW.value


def resolve_locale(
    *,
    explicit: str | None = None,
    accept_language: str | None = None,
    default: str = _DEFAULT,
) -> str:
    """Prefer explicit locale, then Accept-Language, then default."""
    if explicit is not None and explicit.strip():
        return normalize_locale(explicit, default=default)
    if accept_language is not None and accept_language.strip():
        # Take the first language range from Accept-Language.
        first = accept_language.split(",", maxsplit=1)[0]
        return normalize_locale(first, default=default)
    return normalize_locale(default, default=SupportedLocale.HEBREW.value)


def is_rtl(locale: str) -> bool:
    return normalize_locale(locale) in {SupportedLocale.HEBREW.value, SupportedLocale.ARABIC.value}
