"""Deterministic geometry helpers for layout-aware payslip parsing.

These helpers do not assign payroll meaning by themselves.
"""

from __future__ import annotations

from typing import Sequence


BBox = tuple[float, float, float, float] | list[float]


def horizontal_distance(a: BBox, b: BBox) -> float:
    ax, _ay, aw, _ah = (float(v) for v in a)
    bx, _by, bw, _bh = (float(v) for v in b)
    a_right = ax + aw
    b_right = bx + bw
    if a_right < bx:
        return bx - a_right
    if b_right < ax:
        return ax - b_right
    return 0.0


def vertical_overlap_ratio(a: BBox, b: BBox) -> float:
    _ax, ay, _aw, ah = (float(v) for v in a)
    _bx, by, _bw, bh = (float(v) for v in b)
    a_bottom = ay + ah
    b_bottom = by + bh
    overlap = max(0.0, min(a_bottom, b_bottom) - max(ay, by))
    denom = max(min(ah, bh), 1e-9)
    return overlap / denom


def same_line(a: BBox, b: BBox, *, min_overlap: float = 0.5) -> bool:
    return vertical_overlap_ratio(a, b) >= min_overlap


def normalized_distance(a: BBox, b: BBox, *, page_width: float, page_height: float) -> float:
    ax, ay, aw, ah = (float(v) for v in a)
    bx, by, bw, bh = (float(v) for v in b)
    acx, acy = ax + aw / 2.0, ay + ah / 2.0
    bcx, bcy = bx + bw / 2.0, by + bh / 2.0
    dx = abs(acx - bcx) / max(page_width, 1.0)
    dy = abs(acy - bcy) / max(page_height, 1.0)
    return (dx * dx + dy * dy) ** 0.5


def nearest_index(
    target: BBox,
    candidates: Sequence[BBox],
    *,
    page_width: float,
    page_height: float,
) -> int | None:
    if not candidates:
        return None
    best_i = 0
    best_d = normalized_distance(target, candidates[0], page_width=page_width, page_height=page_height)
    for index, box in enumerate(candidates[1:], start=1):
        dist = normalized_distance(target, box, page_width=page_width, page_height=page_height)
        if dist < best_d:
            best_d = dist
            best_i = index
    return best_i
