import { useMemo, useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  BarChartCard,
  LineChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useAiDashboard } from '../../hooks/useAiDashboard';
import { useAiHistory } from '../../hooks/useAiHistory';
import {
  hasAiTrendData,
  mergeAiHistorySeries,
  providerHistoryToChartRows,
} from '../../lib/ai-monitoring/chart-series';
import './admin-ai.css';

const WINDOW_OPTIONS = [6, 24, 72, 168] as const;

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function BarList({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, value]) => value));
  return (
    <section className="admin-ai-card">
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="admin-ai-muted">No data yet. Usage appears after AI calls.</p>
      ) : (
        <ul className="admin-ai-bars">
          {entries.map(([label, value]) => (
            <li key={label}>
              <div className="admin-ai-bars__label">
                <span>{label}</span>
                <span>{value.toLocaleString()}</span>
              </div>
              <div className="admin-ai-bars__track">
                <div
                  className="admin-ai-bars__fill"
                  style={{ width: `${Math.max(4, (value / max) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SystemDashboardPage() {
  const [windowHours, setWindowHours] = useState(24);
  const dashboard = useAiDashboard(windowHours);
  const history = useAiHistory(windowHours);

  const trendRows = useMemo(
    () =>
      mergeAiHistorySeries({
        tokens: history.data?.tokens ?? [],
        cost_usd: history.data?.cost_usd ?? [],
        latency_ms: history.data?.latency_ms ?? [],
        successes: history.data?.successes ?? [],
        errors: history.data?.errors ?? [],
        retries: history.data?.retries ?? [],
        fallbacks: history.data?.fallbacks ?? [],
      }),
    [history.data],
  );
  const providerRows = useMemo(
    () => providerHistoryToChartRows(history.data?.by_provider ?? []),
    [history.data?.by_provider],
  );
  const hasTrends = hasAiTrendData(trendRows);
  const summary = dashboard.data;
  const loading = (dashboard.loading && !summary) || (history.loading && !history.data);
  const error = dashboard.error || history.error;

  return (
    <PortalPage
      title="System Dashboard"
      description="Developer AI monitoring: tokens, cost, latency, reliability, and historical trends."
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

      {loading ? <AnalyticsLoadingState cards={4} label="Loading AI metrics" /> : null}

      {error ? (
        <AnalyticsErrorState
          title="Unable to load AI monitoring"
          message={error}
          onRetry={() => {
            dashboard.reload();
            history.reload();
          }}
        />
      ) : null}

      {!loading && !error && summary && summary.request_count === 0 && !hasTrends ? (
        <AnalyticsEmptyState
          title="No AI metrics yet"
          description="Metrics appear after AI calls. Historical trends use CloudWatch when enabled, otherwise this process."
        />
      ) : null}

      {summary && (summary.request_count > 0 || hasTrends) ? (
        <div className="admin-ai">
          <div className="admin-ai-kpis">
            <div className="admin-ai-kpi">
              <span>Total tokens</span>
              <strong>{summary.total_tokens.toLocaleString()}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Estimated cost</span>
              <strong>${summary.estimated_cost_usd.toFixed(4)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Average latency</span>
              <strong>{summary.average_latency_ms.toFixed(0)} ms</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Error rate</span>
              <strong>{pct(summary.error_rate)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Retry rate</span>
              <strong>{pct(summary.retry_rate)}</strong>
            </div>
            <div className="admin-ai-kpi">
              <span>Fallback rate</span>
              <strong>{pct(summary.fallback_rate)}</strong>
            </div>
          </div>

          <div className="admin-ai-grid">
            <BarList title="Tokens by provider" data={summary.tokens_by_provider} />
            <BarList title="Tokens by model" data={summary.tokens_by_model} />
            <BarList
              title="Tokens by capability"
              data={summary.tokens_by_capability ?? {}}
            />
            {summary.prompt_versions && Object.keys(summary.prompt_versions).length > 0 ? (
              <BarList title="Prompt versions" data={summary.prompt_versions} />
            ) : null}
          </div>

          {hasTrends ? (
            <>
              <LineChartCard
                title="Tokens & cost trends"
                data={trendRows}
                xKey="time"
                series={[
                  {
                    dataKey: 'tokens',
                    name: 'Tokens',
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                  {
                    dataKey: 'cost',
                    name: 'Cost USD',
                    color: ANALYTICS_CHART_COLORS.secondary,
                  },
                ]}
              />
              <LineChartCard
                title="Latency trend"
                data={trendRows}
                xKey="time"
                yLabel="ms"
                series={[
                  {
                    dataKey: 'latency',
                    name: 'Avg latency',
                    color: ANALYTICS_CHART_COLORS.warning,
                  },
                ]}
              />
              <LineChartCard
                title="Success / error / retry / fallback"
                data={trendRows}
                xKey="time"
                series={[
                  {
                    dataKey: 'successes',
                    name: 'Success',
                    color: ANALYTICS_CHART_COLORS.secondary,
                  },
                  {
                    dataKey: 'errors',
                    name: 'Errors',
                    color: ANALYTICS_CHART_COLORS.danger,
                  },
                  {
                    dataKey: 'retries',
                    name: 'Retries',
                    color: ANALYTICS_CHART_COLORS.warning,
                  },
                  {
                    dataKey: 'fallbacks',
                    name: 'Fallbacks',
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                ]}
              />
            </>
          ) : (
            <AnalyticsEmptyState
              title="No historical trend points yet"
              description="Trends populate from CloudWatch when enabled, or from hourly process-local buckets after AI traffic."
            />
          )}

          {providerRows.length > 0 ? (
            <BarChartCard
              title="Provider comparison (window)"
              data={providerRows}
              xKey="name"
              series={[
                {
                  dataKey: 'tokens',
                  name: 'Tokens',
                  color: ANALYTICS_CHART_COLORS.primary,
                },
                {
                  dataKey: 'requests',
                  name: 'Requests',
                  color: ANALYTICS_CHART_COLORS.secondary,
                },
                {
                  dataKey: 'errors',
                  name: 'Errors',
                  color: ANALYTICS_CHART_COLORS.danger,
                },
                {
                  dataKey: 'retries',
                  name: 'Retries',
                  color: ANALYTICS_CHART_COLORS.warning,
                },
              ]}
            />
          ) : null}

          <p className="admin-ai-muted">
            Requests observed: {summary.request_count.toLocaleString()}. Snapshot source:{' '}
            {summary.source}. History source: {history.data?.source ?? '—'}.
          </p>
        </div>
      ) : null}
    </PortalPage>
  );
}
