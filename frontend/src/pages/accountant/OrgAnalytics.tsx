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
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import { useOrgPayrollAnalytics } from '../../hooks/useOrgPayrollAnalytics';
import {
  confidenceToChartRows,
  errorBucketsToChartRows,
  outcomesToChartRows,
  validationFailuresToChartRows,
} from '../../lib/analytics/chart-series';

export function OrgAnalyticsPage() {
  const { t } = useTranslation();
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, loading, error, reload } = useOrgPayrollAnalytics(year);

  const outcomes = useMemo(
    () => outcomesToChartRows(data?.documents_by_month ?? []),
    [data?.documents_by_month],
  );
  const failures = useMemo(
    () => validationFailuresToChartRows(data?.validation_failures_by_month ?? []),
    [data?.validation_failures_by_month],
  );
  const errorTypes = useMemo(
    () => errorBucketsToChartRows(data?.error_type_distribution ?? []),
    [data?.error_type_distribution],
  );
  const topFailures = useMemo(
    () => errorBucketsToChartRows(data?.top_validation_failures ?? []),
    [data?.top_validation_failures],
  );
  const confidence = useMemo(
    () => confidenceToChartRows(data?.average_confidence_by_month ?? []),
    [data?.average_confidence_by_month],
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

  const hasData =
    outcomes.length > 0 ||
    failures.length > 0 ||
    errorTypes.length > 0 ||
    confidence.length > 0;

  return (
    <PortalPage
      title={t('accountant.analytics.pageTitle')}
      description={t('accountant.analytics.pageDescription')}
    >
      <AnalyticsDashboardLayout
        toolbar={
          <AnalyticsYearFilter
            label={t('accountant.analytics.yearLabel')}
            year={year}
            years={data?.available_years ?? [year]}
            onChange={setYear}
            disabled={loading}
          />
        }
      >
        {loading && !data ? <AnalyticsLoadingState cards={4} /> : null}

        {error ? (
          <AnalyticsErrorState
            title={t('accountant.analytics.errorTitle')}
            message={error}
            onRetry={reload}
            retryLabel={t('common.retry')}
          />
        ) : null}

        {!loading && !error && data && !hasData ? (
          <AnalyticsEmptyState
            title={t('accountant.analytics.emptyTitle')}
            description={t('accountant.analytics.emptyDescription')}
          />
        ) : null}

        {data && hasData ? (
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
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
