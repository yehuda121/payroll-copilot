import { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
    <PortalPage title={t('admin.aiModels.title')} description={t('admin.aiModels.description')}>
      <div className="admin-ai-toolbar">
        <label className="admin-ai-window">
          <span>{t('admin.aiModels.window')}</span>
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

      {loading && rows.length === 0 ? (
        <AnalyticsLoadingState cards={3} label={t('common.loading')} />
      ) : null}

      {error ? (
        <AnalyticsErrorState title={t('common.error')} message={error} onRetry={reload} />
      ) : null}

      {!loading && !error && rows.length === 0 ? (
        <AnalyticsEmptyState
          title={t('admin.aiModels.empty')}
          description={t('admin.dashboard.emptyHint')}
        />
      ) : null}

      {rows.length > 0 ? (
        <div className="admin-ai">
          <section className="admin-dashboard-section">
            <header className="admin-dashboard-section__header">
              <h2>{t('admin.nav.groups.aiPlatform')}</h2>
              <p>{t('admin.aiModels.description')}</p>
            </header>
            <BarChartCard
              title={t('admin.aiModels.requestsReliability')}
              data={chartRows}
              xKey="name"
              layout="vertical"
              series={[
                {
                  dataKey: 'requests',
                  name: t('admin.dashboard.series.requests'),
                  color: ANALYTICS_CHART_COLORS.primary,
                },
                {
                  dataKey: 'success',
                  name: t('admin.dashboard.kpi.successRate'),
                  color: ANALYTICS_CHART_COLORS.secondary,
                },
                {
                  dataKey: 'errors',
                  name: t('admin.dashboard.kpi.errorRate'),
                  color: ANALYTICS_CHART_COLORS.danger,
                },
                {
                  dataKey: 'retries',
                  name: t('admin.dashboard.kpi.retries'),
                  color: ANALYTICS_CHART_COLORS.warning,
                },
              ]}
            />
          </section>

          <div className="admin-ai-table-wrap">
            <table className="admin-ai-table">
              <thead>
                <tr>
                  <th>{t('admin.aiModels.colProvider')}</th>
                  <th>{t('admin.aiModels.colModel')}</th>
                  <th>{t('admin.aiModels.colRequests')}</th>
                  <th>{t('admin.aiModels.colLatency')}</th>
                  <th>{t('admin.aiModels.colTokens')}</th>
                  <th>{t('admin.aiModels.colCost')}</th>
                  <th>{t('admin.aiModels.colSuccess')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.provider}-${row.model}-${row.capability ?? 'default'}`}>
                    <td>{row.provider}</td>
                    <td>{row.model}</td>
                    <td>{row.request_count.toLocaleString()}</td>
                    <td>{row.average_latency_ms.toFixed(0)} ms</td>
                    <td>{row.average_tokens.toLocaleString()}</td>
                    <td>${row.estimated_cost_usd.toFixed(4)}</td>
                    <td>{pct(row.success_rate)}</td>
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
