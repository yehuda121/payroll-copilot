import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AnalyticsDashboardLayout,
  AnalyticsStatGrid,
} from './AnalyticsDashboardLayout';
import { AnalyticsEmptyState } from './AnalyticsEmptyState';
import { AnalyticsErrorState } from './AnalyticsErrorState';
import { AnalyticsLoadingState } from './AnalyticsLoadingState';
import { AnalyticsStatCard } from './AnalyticsStatCard';
import { AnalyticsYearFilter } from './AnalyticsYearFilter';
import { BarChartCard } from './charts/BarChartCard';
import { LineChartCard } from './charts/LineChartCard';
import { ANALYTICS_CHART_COLORS } from './chartColors';
import { useEmployeeSalaryAnalytics } from '../../hooks/useEmployeeSalaryAnalytics';
import {
  hasSalaryChartData,
  salaryMonthsToChartRows,
} from '../../lib/analytics/chart-series';
import './analytics.css';

type EmployeeSalaryAnalyticsPanelProps = {
  initialYear?: number;
};

export function EmployeeSalaryAnalyticsPanel({
  initialYear = new Date().getFullYear(),
}: EmployeeSalaryAnalyticsPanelProps) {
  const { t } = useTranslation();
  const [year, setYear] = useState(initialYear);
  const { data, loading, error, reload } = useEmployeeSalaryAnalytics(year);

  const chartRows = useMemo(
    () => salaryMonthsToChartRows(data?.months ?? []),
    [data?.months],
  );
  const years = data?.available_years ?? [year];
  const withNet = chartRows.filter((row) => row.net != null).length;
  const withGross = chartRows.filter((row) => row.gross != null).length;

  return (
    <AnalyticsDashboardLayout
      toolbar={
        <AnalyticsYearFilter
          label={t('employee.payslips.yearLabel')}
          year={year}
          years={years}
          onChange={setYear}
          disabled={loading}
        />
      }
    >
      {loading && !data ? <AnalyticsLoadingState /> : null}

      {error ? (
        <AnalyticsErrorState
          title={t('employee.analytics.errorTitle')}
          message={error}
          onRetry={reload}
          retryLabel={t('common.retry')}
        />
      ) : null}

      {!loading && !error && data && !hasSalaryChartData(chartRows) ? (
        <AnalyticsEmptyState
          title={t('employee.analytics.emptyTitle')}
          description={t('employee.analytics.emptyDescription')}
        />
      ) : null}

      {data && hasSalaryChartData(chartRows) ? (
        <>
          <AnalyticsStatGrid>
            <AnalyticsStatCard
              label={t('employee.analytics.monthsWithNet')}
              value={withNet}
            />
            <AnalyticsStatCard
              label={t('employee.analytics.monthsWithGross')}
              value={withGross}
            />
            <AnalyticsStatCard
              label={t('employee.analytics.currency')}
              value={data.months[0]?.currency || 'ILS'}
            />
          </AnalyticsStatGrid>

          <LineChartCard
            title={t('employee.analytics.netLineTitle')}
            data={chartRows}
            xKey="period"
            series={[
              {
                dataKey: 'net',
                name: t('employee.analytics.netSeries'),
                color: ANALYTICS_CHART_COLORS.primary,
              },
            ]}
          />

          <BarChartCard
            title={t('employee.analytics.grossVsNetTitle')}
            data={chartRows}
            xKey="period"
            series={[
              {
                dataKey: 'gross',
                name: t('employee.analytics.grossSeries'),
                color: ANALYTICS_CHART_COLORS.secondary,
              },
              {
                dataKey: 'net',
                name: t('employee.analytics.netSeries'),
                color: ANALYTICS_CHART_COLORS.primary,
              },
            ]}
          />
        </>
      ) : null}
    </AnalyticsDashboardLayout>
  );
}
