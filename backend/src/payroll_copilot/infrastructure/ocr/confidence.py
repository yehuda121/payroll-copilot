"""Shared confidence helpers for OCR providers. Never invent confidence."""

from __future__ import annotations


def average_confidence(values: list[float]) -> float | None:
    """Return the mean of real OCR confidences, or None when none exist."""
    if not values:
        return None
    return sum(values) / len(values)


def normalize_paddle_score(score: object) -> float | None:
    """Normalize a PaddleOCR score to [0, 1]. Returns None if missing/invalid."""
    try:
        value = float(score)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    if value > 1.0:
        # Some builds report 0–100
        if value <= 100.0:
            return value / 100.0
        return None
    return value
