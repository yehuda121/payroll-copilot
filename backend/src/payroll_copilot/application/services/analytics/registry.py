"""Extensible analytics metric registry.

Future metrics register a provider — no central switch statement required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AnalyticsContext:
    """Shared request context passed to metric providers."""

    organization_id: UUID | None = None
    employee_id: UUID | None = None
    year: int | None = None
    params: dict[str, Any] = field(default_factory=dict)


class AnalyticsMetricProvider(Protocol):
    """Compute one named analytics result from existing repositories."""

    metric_name: str

    async def compute(self, context: AnalyticsContext) -> Any: ...


class AnalyticsRegistry:
    """Name → provider map. Adding a metric = register + use case + route."""

    def __init__(self) -> None:
        self._providers: dict[str, AnalyticsMetricProvider] = {}

    def register(self, provider: AnalyticsMetricProvider) -> None:
        name = str(provider.metric_name).strip()
        if not name:
            raise ValueError("metric_name must be non-empty")
        self._providers[name] = provider

    def get(self, metric_name: str) -> AnalyticsMetricProvider:
        try:
            return self._providers[metric_name]
        except KeyError as exc:
            raise KeyError(f"Unknown analytics metric: {metric_name}") from exc

    def names(self) -> list[str]:
        return sorted(self._providers)

    async def compute(self, metric_name: str, context: AnalyticsContext) -> Any:
        return await self.get(metric_name).compute(context)
