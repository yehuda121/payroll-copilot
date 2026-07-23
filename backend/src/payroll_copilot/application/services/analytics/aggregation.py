"""Pure aggregation helpers for analytics series (extensible, no persistence)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from typing import Any, Callable, TypeVar

T = TypeVar("T")
K = TypeVar("K")


def group_by(items: Iterable[T], key_fn: Callable[[T], K]) -> dict[K, list[T]]:
    grouped: dict[K, list[T]] = defaultdict(list)
    for item in items:
        grouped[key_fn(item)].append(item)
    return dict(grouped)


def count_by(items: Iterable[T], key_fn: Callable[[T], K]) -> Counter[K]:
    return Counter(key_fn(item) for item in items)


def average(values: Iterable[float]) -> float | None:
    nums = [float(v) for v in values]
    if not nums:
        return None
    return sum(nums) / len(nums)


def top_n(counter: Counter[Any], *, limit: int = 10) -> list[tuple[Any, int]]:
    return counter.most_common(max(0, limit))


def sorted_period_keys(keys: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted({(int(y), int(m)) for y, m in keys}, key=lambda p: (p[0], p[1]))


def iter_unique_keep_last(
    items: Iterable[T],
    *,
    key_fn: Callable[[T], K],
) -> Iterator[T]:
    """Keep the last occurrence for each key (caller should order items ascending)."""
    last: dict[K, T] = {}
    for item in items:
        last[key_fn(item)] = item
    yield from last.values()
