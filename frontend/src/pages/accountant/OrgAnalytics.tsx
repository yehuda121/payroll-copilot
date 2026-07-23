import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsDashboardLayout,
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  AnalyticsStatCard,
  AnalyticsStatGrid,
  AnalyticsYearFilter,
  BarChartCard,
  DonutChartCard,
  LineChartCard,
  QualityAnalyticsPanel,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useOrgPayrollAnalytics } from '../../hooks/useOrgPayrollAnalytics';
import { useOrgQualityAnalytics } from '../../hooks/useOrgQualityAnalytics';
import {
  confidenceToChartRows,
  errorBucketsToChartRows,
  outcomesToChartRows,
  validationFailuresToChartRows,
} from '../../lib/analytics/chart-series';

type AnalyticsTab = 'payroll' | 'quality';

export function OrgAnalyticsPage() {
  const { t } = useTranslation();
  const [year, setYear] = useState(new Date().getFullYear());
  const [tab, setTab] = useState<AnalyticsTab>('payroll');
  const payroll = useOrgPayrollAnalytics(year);
  const quality = useOrgQualityAnalytics(year);

  const outcomes = useMemo(
    () => outcomesToChartRows(payroll.data?.documents_by_month ?? []),
    [payroll.data?.documents_by_month],
  );
  const failures = useMemo(
    () => validationFailuresToChartRows(payroll.data?.validation_failures_by_month ?? []),
    [payroll.data?.validation_failures_by_month],
  );
  const errorTypes = useMemo(
    () => errorBucketsToChartRows(payroll.data?.error_type_distribution ?? []),
    [payroll.data?.error_type_distribution],
  );
  const topFailures = useMemo(
    () => errorBucketsToChartRows(payroll.data?.top_validation_failures ?? []),
    [payroll.data?.top_validation_failures],
  );
  const confidence = useMemo(
    () => confidenceToChartRows(payroll.data?.average_confidence_by_month ?? []),
    [payroll.data?.average_confidence_by_month],
  );

  const totals = useMemo(() => {
    return outcomes.reduce(
      (acc, row) => {
        acc.processed += row.processed;
        acc.success += row.success;
        acc.review += row.reviewRequired;
        acc.failed += row.failed;
        return acc;
      },
      { processed: 0, success: 0, review: 0, failed: 0 },
    );
  }, [outcomes]);

  const outcomeDonut = [
    { name: t('accountant.analytics.outcomeSuccess'), value: totals.success },
    { name: t('accountant.analytics.outcomeReview'), value: totals.review },
    { name: t('accountant.analytics.outcomeFailed'), value: totals.failed },
  ].filter((row) => row.value > 0);

  const hasPayrollData =
    outcomes.length > 0 ||
    failures.length > 0 ||
    errorTypes.length > 0 ||
    confidence.length > 0;

  const availableYears = Array.from(
    new Set([
      ...(payroll.data?.available_years ?? []),
      ...(quality.data?.available_years ?? []),
      year,
    ]),
  ).sort((a, b) => b - a);

  const loading = tab === 'payroll' ? payroll.loading : quality.loading;

  return (
    <PortalPage
      title={t('accountant.analytics.pageTitle')}
      description={t('accountant.analytics.pageDescription')}
    >
      <div className="employee-review-tabs" role="tablist" aria-label={t('accountant.analytics.pageTitle')}>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'payroll'}
          className={`employee-review-tabs__tab ${tab === 'payroll' ? 'is-active' : ''}`}
          onClick={() => setTab('payroll')}
        >
          {t('accountant.analytics.tabs.payroll')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'quality'}
          className={`employee-review-tabs__tab ${tab === 'quality' ? 'is-active' : ''}`}
          onClick={() => setTab('quality')}
        >
          {t('accountant.analytics.tabs.quality')}
        </button>
      </div>

      <AnalyticsDashboardLayout
        toolbar={
          <AnalyticsYearFilter
            label={t('accountant.analytics.yearLabel')}
            year={year}
            years={availableYears}
            onChange={setYear}
            disabled={loading}
          />
        }
      >
        {tab === 'payroll' ? (
          <>
            {payroll.loading && !payroll.data ? <AnalyticsLoadingState cards={4} /> : null}

            {payroll.error ? (
              <AnalyticsErrorState
                title={t('accountant.analytics.errorTitle')}
                message={payroll.error}
                onRetry={payroll.reload}
                retryLabel={t('common.retry')}
              />
            ) : null}

            {!payroll.loading && !payroll.error && payroll.data && !hasPayrollData ? (
              <AnalyticsEmptyState
                title={t('accountant.analytics.emptyTitle')}
                description={t('accountant.analytics.emptyDescription')}
              />
            ) : null}

            {payroll.data && hasPayrollData ? (
              <>
                <AnalyticsStatGrid>
                  <AnalyticsStatCard
                    label={t('accountant.analytics.documentsProcessed')}
                    value={totals.processed}
                  />
                  <AnalyticsStatCard
                    label={t('accountant.analytics.outcomeSuccess')}
                    value={totals.success}
                  />
                  <AnalyticsStatCard
                    label={t('accountant.analytics.outcomeReview')}
                    value={totals.review}
                  />
                  <AnalyticsStatCard
                    label={t('accountant.analytics.outcomeFailed')}
                    value={totals.failed}
                  />
                </AnalyticsStatGrid>

                <BarChartCard
                  title={t('accountant.analytics.documentsByMonthTitle')}
                  data={outcomes}
                  xKey="period"
                  series={[
                    {
                      dataKey: 'processed',
                      name: t('accountant.analytics.documentsProcessed'),
                      color: ANALYTICS_CHART_COLORS.primary,
                    },
                  ]}
                />

                <BarChartCard
                  title={t('accountant.analytics.outcomesByMonthTitle')}
                  data={outcomes}
                  xKey="period"
                  series={[
                    {
                      dataKey: 'success',
                      name: t('accountant.analytics.outcomeSuccess'),
                      color: ANALYTICS_CHART_COLORS.secondary,
                      stackId: 'outcome',
                    },
                    {
                      dataKey: 'reviewRequired',
                      name: t('accountant.analytics.outcomeReview'),
                      color: ANALYTICS_CHART_COLORS.warning,
                      stackId: 'outcome',
                    },
                    {
                      dataKey: 'failed',
                      name: t('accountant.analytics.outcomeFailed'),
                      color: ANALYTICS_CHART_COLORS.danger,
                      stackId: 'outcome',
                    },
                  ]}
                />

                {outcomeDonut.length > 0 ? (
                  <DonutChartCard
                    title={t('accountant.analytics.outcomeDistributionTitle')}
                    data={outcomeDonut}
                  />
                ) : null}

                {failures.length > 0 ? (
                  <BarChartCard
                    title={t('accountant.analytics.validationFailuresTitle')}
                    data={failures}
                    xKey="period"
                    series={[
                      {
                        dataKey: 'failures',
                        name: t('accountant.analytics.validationFailures'),
                        color: ANALYTICS_CHART_COLORS.danger,
                      },
                    ]}
                  />
                ) : null}

                {errorTypes.length > 0 ? (
                  <DonutChartCard
                    title={t('accountant.analytics.errorTypesTitle')}
                    data={errorTypes.slice(0, 8)}
                  />
                ) : null}

                {topFailures.length > 0 ? (
                  <BarChartCard
                    title={t('accountant.analytics.topFailuresTitle')}
                    data={topFailures.slice(0, 10)}
                    xKey="name"
                    layout="vertical"
                    series={[
                      {
                        dataKey: 'value',
                        name: t('accountant.analytics.validationFailures'),
                        color: ANALYTICS_CHART_COLORS.warning,
                      },
                    ]}
                  />
                ) : null}

                {confidence.length > 0 ? (
                  <LineChartCard
                    title={t('accountant.analytics.confidenceTitle')}
                    data={confidence}
                    xKey="period"
                    yLabel="%"
                    series={[
                      {
                        dataKey: 'confidence',
                        name: t('accountant.analytics.confidenceSeries'),
                        color: ANALYTICS_CHART_COLORS.primary,
                      },
                    ]}
                  />
                ) : null}
              </>
            ) : null}
          </>
        ) : (
          <QualityAnalyticsPanel
            months={quality.data?.months ?? []}
            confidenceDistribution={quality.data?.confidence_distribution ?? []}
            totals={quality.data?.totals}
            loading={quality.loading}
            error={quality.error}
            onRetry={quality.reload}
          />
        )}
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
