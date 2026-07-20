"""Normalize confidence values to a consistent unit interval [0, 1].

Association confidence *bands* (high/medium/low) stay separate — this module
handles numeric scales only (OCR 0–100, provider floats, etc.).
"""

from __future__ import annotations

_BAND_TO_UNIT: dict[str, float | None] = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.45,
    "unknown": None,
}


def normalize_unit_interval_confidence(value: object) -> float | None:
    """Coerce a confidence-like value to [0, 1], or None if missing/invalid.

    Accepts:
    - None / empty → None
    - float/int in [0, 1] → unchanged
    - float/int in (1, 100] → divided by 100 (common OCR 0–100 scale)
    - band strings high|medium|low|unknown → mapped unit scores
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        band = value.strip().lower()
        if band in _BAND_TO_UNIT:
            return _BAND_TO_UNIT[band]
        try:
            number = float(band)
        except ValueError:
            return None
    else:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    if number < 0.0:
        return None
    if number <= 1.0:
        return number
    # Ambiguous (1, 2): not a valid unit interval and not a clear 0–100 reading.
    if number < 2.0:
        return None
    if number <= 100.0:
        return number / 100.0
    return None
