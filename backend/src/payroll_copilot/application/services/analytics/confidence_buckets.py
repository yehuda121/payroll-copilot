"""Confidence histogram helpers for quality analytics (pure, no I/O)."""

from __future__ import annotations

from payroll_copilot.application.dto.analytics import ConfidenceBucket

# Fixed bands for Phase 2 quality dashboards. Last band includes 1.0.
CONFIDENCE_BUCKET_SPECS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.50", 0.0, 0.5),
    ("0.50-0.70", 0.5, 0.7),
    ("0.70-0.85", 0.7, 0.85),
    ("0.85-1.00", 0.85, 1.0001),
)


def empty_confidence_buckets() -> list[ConfidenceBucket]:
    return [
        ConfidenceBucket(label=label, min_inclusive=lo, max_exclusive=hi, count=0)
        for label, lo, hi in CONFIDENCE_BUCKET_SPECS
    ]


def bucket_confidence_values(values: list[float]) -> list[ConfidenceBucket]:
    counts = [0] * len(CONFIDENCE_BUCKET_SPECS)
    for raw in values:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value < 0 or value > 1:
            continue
        for index, (_, lo, hi) in enumerate(CONFIDENCE_BUCKET_SPECS):
            if lo <= value < hi:
                counts[index] += 1
                break
    return [
        ConfidenceBucket(label=label, min_inclusive=lo, max_exclusive=hi, count=counts[i])
        for i, (label, lo, hi) in enumerate(CONFIDENCE_BUCKET_SPECS)
    ]


def rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)
