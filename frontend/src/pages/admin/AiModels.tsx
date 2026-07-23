import { useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  BarChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useAiModelComparison } from '../../hooks/useAiModelComparison';
import './admin-ai.css';

const WINDOW_OPTIONS = [6, 24, 72, 168] as const;

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export function AiModelsPage() {
  const [windowHours, setWindowHours] = useState(24);
  const { data: items, loading, error, reload } = useAiModelComparison(windowHours);
  const rows = items ?? [];

  const chartRows = rows.map((row) => ({
    name: `${row.provider}/${row.model}`,
    requests: row.request_count,
    latency: row.average_latency_ms,
    tokens: row.average_tokens,
    cost: row.estimated_cost_usd,
    success: Number((row.success_rate * 100).toFixed(1)),
    errors: Number(((row.error_rate ?? 0) * 100).toFixed(1)),
    retries: Number(((row.retry_rate ?? 0) * 100).toFixed(1)),
  }));

  return (
    <PortalPage
      title="AI Models"
      description="Operational comparison of providers and models (volume, latency, tokens, cost, success, retries)."
    >
      <div className="admin-ai-toolbar">
        <label className="admin-ai-window">
          <span>Window</span>
          <select
            value={windowHours}
            disabled={loading}
            onChange={(event) => setWindowHours(Number(event.target.value))}
          >
            {WINDOW_OPTIONS.map((hours) => (
              <option key={hours} value={hours}>
                Last {hours}h
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={3} label="Loading comparison" />
      ) : null}

      {error ? (
        <AnalyticsErrorState
          title="Unable to load model comparison"
          message={error}
          onRetry={reload}
        />
      ) : null}

      {!loading && !error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title="No AI calls recorded yet"
          description="Provider/model comparison appears after AI traffic in this process."
        />
      ) : null}

      {rows.length > 0 ? (
        <div className="admin-ai">
          <BarChartCard
            title="Requests & reliability by model"
            data={chartRows}
            xKey="name"
            layout="vertical"
            series={[
              {
                dataKey: 'requests',
                name: 'Requests',
                color: ANALYTICS_CHART_COLORS.primary,
              },
              {
                dataKey: 'success',
                name: 'Success %',
                color: ANALYTICS_CHART_COLORS.secondary,
              },
              {
                dataKey: 'errors',
                name: 'Error %',
                color: ANALYTICS_CHART_COLORS.danger,
              },
              {
                dataKey: 'retries',
                name: 'Retry %',
                color: ANALYTICS_CHART_COLORS.warning,
              },
            ]}
          />

          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Capability</th>
                  <th>Requests</th>
                  <th>Avg latency</th>
                  <th>Avg tokens</th>
                  <th>Est. cost</th>
                  <th>Success</th>
                  <th>Error</th>
                  <th>Retry</th>
                  <th>Fallback</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.provider}:${row.model}:${row.capability ?? ''}`}>
                    <td>{row.provider}</td>
                    <td>{row.model}</td>
                    <td>{row.capability || '—'}</td>
                    <td>{row.request_count}</td>
                    <td>{row.average_latency_ms.toFixed(0)} ms</td>
                    <td>{row.average_tokens.toFixed(1)}</td>
                    <td>${row.estimated_cost_usd.toFixed(4)}</td>
                    <td>{pct(row.success_rate)}</td>
                    <td>{pct(row.error_rate ?? 0)}</td>
                    <td>{pct(row.retry_rate ?? 0)}</td>
                    <td>{pct(row.fallback_rate ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </PortalPage>
  );
}
