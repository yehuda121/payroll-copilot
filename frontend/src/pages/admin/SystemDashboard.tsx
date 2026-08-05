import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
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
import { AdminEmployeeResetPanel } from './AdminEmployeeResetPanel';
import './admin-ai.css';

const WINDOW_OPTIONS = [6, 24, 72, 168] as const;

function pct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function BarList({
  title,
  data,
  emptyLabel,
}: {
  title: string;
  data: Record<string, number>;
  emptyLabel: string;
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, value]) => value));
  return (
    <section className="admin-ai-card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className="admin-ai-muted">{emptyLabel}</p>
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

function DashboardSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="admin-dashboard-section">
      <header className="admin-dashboard-section__header">
        <h2>{title}</h2>
        <p>{description}</p>
      </header>
      <div className="admin-dashboard-section__body">{children}</div>
    </section>
  );
}

export function SystemDashboardPage() {
  const { t } = useTranslation();
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
    <PortalPage title={t('admin.dashboard.title')} description={t('admin.dashboard.description')}>
      <div className="admin-ai-toolbar">
        <label className="admin-ai-window">
          <span>{t('admin.dashboard.window')}</span>
          <select
            className="pc-form-control pc-form-control--select"
            value={windowHours}
            disabled={loading}
            onChange={(event) => setWindowHours(Number(event.target.value))}
          >
            {WINDOW_OPTIONS.map((hours) => (
              <option key={hours} value={hours}>
                {t('admin.dashboard.windowHours', { hours })}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <AnalyticsLoadingState cards={4} label={t('admin.dashboard.loading')} />
      ) : null}

      {error ? (
        <AnalyticsErrorState
          title={t('common.error')}
          message={error}
          onRetry={() => {
            dashboard.reload();
            history.reload();
          }}
        />
      ) : null}

      {!loading && !error && summary && summary.request_count === 0 && !hasTrends ? (
        <AnalyticsEmptyState
          title={t('admin.dashboard.empty')}
          description={t('admin.dashboard.emptyHint')}
        />
      ) : null}

      {summary && (summary.request_count > 0 || hasTrends) ? (
        <div className="admin-ai">
          <DashboardSection
            title={t('admin.dashboard.sections.overview.title')}
            description={t('admin.dashboard.sections.overview.description')}
          >
            <div className="admin-ai-kpis">
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.tokens')}</span>
                <strong>{summary.total_tokens.toLocaleString()}</strong>
              </div>
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.cost')}</span>
                <strong>${summary.estimated_cost_usd.toFixed(4)}</strong>
              </div>
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.avgLatency')}</span>
                <strong>{summary.average_latency_ms.toFixed(0)} ms</strong>
              </div>
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.errorRate')}</span>
                <strong>{pct(summary.error_rate)}</strong>
              </div>
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.retries')}</span>
                <strong>{pct(summary.retry_rate)}</strong>
              </div>
              <div className="admin-ai-kpi">
                <span>{t('admin.dashboard.kpi.fallbacks')}</span>
                <strong>{pct(summary.fallback_rate)}</strong>
              </div>
            </div>
          </DashboardSection>

          <DashboardSection
            title={t('admin.dashboard.sections.usage.title')}
            description={t('admin.dashboard.sections.usage.description')}
          >
            <div className="admin-ai-grid">
              <BarList
                title={t('admin.dashboard.charts.byProvider')}
                data={summary.tokens_by_provider}
                emptyLabel={t('admin.dashboard.emptyHint')}
              />
              <BarList
                title={t('admin.dashboard.charts.byModel')}
                data={summary.tokens_by_model}
                emptyLabel={t('admin.dashboard.emptyHint')}
              />
              <BarList
                title={t('admin.dashboard.charts.byCapability')}
                data={summary.tokens_by_capability ?? {}}
                emptyLabel={t('admin.dashboard.emptyHint')}
              />
              {summary.prompt_versions && Object.keys(summary.prompt_versions).length > 0 ? (
                <BarList
                  title={t('admin.dashboard.charts.byPrompt')}
                  data={summary.prompt_versions}
                  emptyLabel={t('admin.dashboard.emptyHint')}
                />
              ) : null}
            </div>
          </DashboardSection>

          <DashboardSection
            title={t('admin.dashboard.sections.trends.title')}
            description={t('admin.dashboard.sections.trends.description')}
          >
            {hasTrends ? (
              <>
                <LineChartCard
                  title={t('admin.dashboard.charts.tokensCost')}
                  data={trendRows}
                  xKey="time"
                  series={[
                    {
                      dataKey: 'tokens',
                      name: t('admin.dashboard.series.tokens'),
                      color: ANALYTICS_CHART_COLORS.primary,
                    },
                    {
                      dataKey: 'cost',
                      name: t('admin.dashboard.series.cost'),
                      color: ANALYTICS_CHART_COLORS.secondary,
                    },
                  ]}
                />
                <LineChartCard
                  title={t('admin.dashboard.charts.latency')}
                  data={trendRows}
                  xKey="time"
                  yLabel="ms"
                  series={[
                    {
                      dataKey: 'latency',
                      name: t('admin.dashboard.series.latency'),
                      color: ANALYTICS_CHART_COLORS.warning,
                    },
                  ]}
                />
                <LineChartCard
                  title={t('admin.dashboard.charts.reliability')}
                  data={trendRows}
                  xKey="time"
                  series={[
                    {
                      dataKey: 'successes',
                      name: t('admin.dashboard.series.successes'),
                      color: ANALYTICS_CHART_COLORS.secondary,
                    },
                    {
                      dataKey: 'errors',
                      name: t('admin.dashboard.series.errors'),
                      color: ANALYTICS_CHART_COLORS.danger,
                    },
                    {
                      dataKey: 'retries',
                      name: t('admin.dashboard.series.retries'),
                      color: ANALYTICS_CHART_COLORS.warning,
                    },
                    {
                      dataKey: 'fallbacks',
                      name: t('admin.dashboard.series.fallbacks'),
                      color: ANALYTICS_CHART_COLORS.primary,
                    },
                  ]}
                />
              </>
            ) : (
              <AnalyticsEmptyState
                title={t('admin.dashboard.charts.noTrend')}
                description={t('admin.dashboard.emptyHint')}
              />
            )}
          </DashboardSection>

          {providerRows.length > 0 ? (
            <DashboardSection
              title={t('admin.dashboard.sections.providers.title')}
              description={t('admin.dashboard.sections.providers.description')}
            >
              <BarChartCard
                title={t('admin.dashboard.charts.providerCompare')}
                data={providerRows}
                xKey="name"
                series={[
                  {
                    dataKey: 'tokens',
                    name: t('admin.dashboard.series.tokens'),
                    color: ANALYTICS_CHART_COLORS.primary,
                  },
                  {
                    dataKey: 'requests',
                    name: t('admin.dashboard.series.requests'),
                    color: ANALYTICS_CHART_COLORS.secondary,
                  },
                  {
                    dataKey: 'errors',
                    name: t('admin.dashboard.series.errors'),
                    color: ANALYTICS_CHART_COLORS.danger,
                  },
                  {
                    dataKey: 'retries',
                    name: t('admin.dashboard.series.retries'),
                    color: ANALYTICS_CHART_COLORS.warning,
                  },
                ]}
              />
            </DashboardSection>
          ) : null}
        </div>
      ) : null}

      <AdminEmployeeResetPanel
        onSuccess={() => {
          dashboard.reload();
          history.reload();
        }}
      />
    </PortalPage>
  );
}
