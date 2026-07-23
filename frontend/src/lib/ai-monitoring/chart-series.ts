/**
 * Pure mappers for AI observability trend charts.
 */

import type { HistoryPoint, ProviderHistoryItem } from '../../services/aiMonitoring';

export type AiTrendRow = {
  time: string;
  tokens: number | null;
  cost: number | null;
  latency: number | null;
  successes: number | null;
  errors: number | null;
  retries: number | null;
  fallbacks: number | null;
};

function shortTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function indexByTime(points: HistoryPoint[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const point of points) {
    map.set(point.timestamp, point.value);
  }
  return map;
}

export function mergeAiHistorySeries(input: {
  tokens: HistoryPoint[];
  cost_usd: HistoryPoint[];
  latency_ms: HistoryPoint[];
  successes: HistoryPoint[];
  errors: HistoryPoint[];
  retries: HistoryPoint[];
  fallbacks: HistoryPoint[];
}): AiTrendRow[] {
  const times = Array.from(
    new Set([
      ...input.tokens.map((p) => p.timestamp),
      ...input.cost_usd.map((p) => p.timestamp),
      ...input.latency_ms.map((p) => p.timestamp),
      ...input.successes.map((p) => p.timestamp),
      ...input.errors.map((p) => p.timestamp),
      ...input.retries.map((p) => p.timestamp),
      ...input.fallbacks.map((p) => p.timestamp),
    ]),
  ).sort();

  const tokens = indexByTime(input.tokens);
  const cost = indexByTime(input.cost_usd);
  const latency = indexByTime(input.latency_ms);
  const successes = indexByTime(input.successes);
  const errors = indexByTime(input.errors);
  const retries = indexByTime(input.retries);
  const fallbacks = indexByTime(input.fallbacks);

  return times.map((timestamp) => ({
    time: shortTime(timestamp),
    tokens: tokens.has(timestamp) ? (tokens.get(timestamp) ?? null) : null,
    cost: cost.has(timestamp) ? (cost.get(timestamp) ?? null) : null,
    latency: latency.has(timestamp) ? (latency.get(timestamp) ?? null) : null,
    successes: successes.has(timestamp) ? (successes.get(timestamp) ?? null) : null,
    errors: errors.has(timestamp) ? (errors.get(timestamp) ?? null) : null,
    retries: retries.has(timestamp) ? (retries.get(timestamp) ?? null) : null,
    fallbacks: fallbacks.has(timestamp) ? (fallbacks.get(timestamp) ?? null) : null,
  }));
}

export type ProviderCompareRow = {
  name: string;
  tokens: number;
  cost: number;
  latency: number;
  requests: number;
  errors: number;
  retries: number;
  successRate: number;
};

export function providerHistoryToChartRows(
  rows: ProviderHistoryItem[],
): ProviderCompareRow[] {
  return rows.map((row) => ({
    name: row.provider,
    tokens: row.tokens,
    cost: Number(row.estimated_cost_usd.toFixed(4)),
    latency: Number(row.average_latency_ms.toFixed(1)),
    requests: row.request_count,
    errors: row.error_count,
    retries: row.retry_count,
    successRate: Number((row.success_rate * 100).toFixed(1)),
  }));
}

export function hasAiTrendData(rows: AiTrendRow[]): boolean {
  return rows.some(
    (row) =>
      row.tokens != null ||
      row.cost != null ||
      row.latency != null ||
      row.successes != null ||
      row.errors != null ||
      row.retries != null ||
      row.fallbacks != null,
  );
}
