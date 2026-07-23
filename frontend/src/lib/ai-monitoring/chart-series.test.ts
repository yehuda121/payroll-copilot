import { describe, expect, it } from 'vitest';
import {
  hasAiTrendData,
  mergeAiHistorySeries,
  providerHistoryToChartRows,
} from './chart-series';

describe('ai monitoring chart-series', () => {
  it('merges history series by timestamp', () => {
    const rows = mergeAiHistorySeries({
      tokens: [{ timestamp: '2026-07-23T12:00:00+00:00', value: 10 }],
      cost_usd: [{ timestamp: '2026-07-23T12:00:00+00:00', value: 0.2 }],
      latency_ms: [{ timestamp: '2026-07-23T13:00:00+00:00', value: 100 }],
      successes: [],
      errors: [{ timestamp: '2026-07-23T12:00:00+00:00', value: 1 }],
      retries: [],
      fallbacks: [],
    });
    expect(rows).toHaveLength(2);
    expect(rows[0]?.tokens).toBe(10);
    expect(rows[0]?.cost).toBe(0.2);
    expect(rows[0]?.errors).toBe(1);
    expect(rows[1]?.latency).toBe(100);
    expect(hasAiTrendData(rows)).toBe(true);
    expect(hasAiTrendData([])).toBe(false);
  });

  it('maps provider history for comparison charts', () => {
    expect(
      providerHistoryToChartRows([
        {
          provider: 'openai',
          tokens: 100,
          estimated_cost_usd: 0.12345,
          average_latency_ms: 88.12,
          success_count: 9,
          error_count: 1,
          retry_count: 2,
          fallback_count: 0,
          request_count: 10,
          success_rate: 0.9,
        },
      ]),
    ).toEqual([
      {
        name: 'openai',
        tokens: 100,
        cost: 0.1235,
        latency: 88.1,
        requests: 10,
        errors: 1,
        retries: 2,
        successRate: 90,
      },
    ]);
  });
});
