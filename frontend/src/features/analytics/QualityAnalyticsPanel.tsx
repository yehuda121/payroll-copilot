import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AnalyticsEmptyState,
  AnalyticsErrorState,
  AnalyticsLoadingState,
  AnalyticsStatCard,
  AnalyticsStatGrid,
  BarChartCard,
  DonutChartCard,
  LineChartCard,
} from '../../features/analytics';
import { ANALYTICS_CHART_COLORS } from '../../features/analytics/chartColors';
import {
  confidenceBucketsToChartRows,
  hasQualityChartData,
  qualityRatesToChartRows,
  qualityVolumesToChartRows,
} from '../../lib/analytics/chart-series';
import type { QualityMonthPoint } from '../../types/analytics';

type QualityAnalyticsPanelProps = {
  months: QualityMonthPoint[];
  confidenceDistribution: Parameters<typeof confidenceBucketsToChartRows>[0];
  totals: QualityMonthPoint | null | undefined;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  /** Prefix for i18n keys under accountant.analytics.quality.* or admin hard-coded fallbacks. */
  titleKeys?: {
    errorTitle: string;
    emptyTitle: string;
    emptyDescription: string;
  };
  labels?: {
    documentsProcessed: string;
    extractionSuccessRate: string;
    validationSuccessRate: string;
    averageConfidence: string;
    manualReviewRate: string;
    failedDocuments: string;
    ratesByMonthTitle: string;
    volumesByMonthTitle: string;
    confidenceDistributionTitle: string;
    ocrSuccess: string;
    ocrFailed: string;
    manualReview: string;
    extractionRateSeries: string;
    validationRateSeries: string;
    manualReviewRateSeries: string;
    confidenceSeries: string;
  };
};

function formatRate(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function formatConfidence(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

export function QualityAnalyticsPanel({
  months,
  confidenceDistribution,
  totals,
  loading,
  error,
  onRetry,
  titleKeys,
  labels,
}: QualityAnalyticsPanelProps) {
  const { t } = useTranslation();

  const L = {
    documentsProcessed:
      labels?.documentsProcessed ?? t('accountant.analytics.quality.documentsProcessed'),
    extractionSuccessRate:
      labels?.extractionSuccessRate ?? t('accountant.analytics.quality.extractionSuccessRate'),
    validationSuccessRate:
      labels?.validationSuccessRate ?? t('accountant.analytics.quality.validationSuccessRate'),
    averageConfidence:
      labels?.averageConfidence ?? t('accountant.analytics.quality.averageConfidence'),
    manualReviewRate:
      labels?.manualReviewRate ?? t('accountant.analytics.quality.manualReviewRate'),
    failedDocuments: labels?.failedDocuments ?? t('accountant.analytics.quality.failedDocuments'),
    ratesByMonthTitle:
      labels?.ratesByMonthTitle ?? t('accountant.analytics.quality.ratesByMonthTitle'),
    volumesByMonthTitle:
      labels?.volumesByMonthTitle ?? t('accountant.analytics.quality.volumesByMonthTitle'),
    confidenceDistributionTitle:
      labels?.confidenceDistributionTitle ??
      t('accountant.analytics.quality.confidenceDistributionTitle'),
    ocrSuccess: labels?.ocrSuccess ?? t('accountant.analytics.quality.ocrSuccess'),
    ocrFailed: labels?.ocrFailed ?? t('accountant.analytics.quality.ocrFailed'),
    manualReview: labels?.manualReview ?? t('accountant.analytics.quality.manualReview'),
    extractionRateSeries:
      labels?.extractionRateSeries ?? t('accountant.analytics.quality.extractionRateSeries'),
    validationRateSeries:
      labels?.validationRateSeries ?? t('accountant.analytics.quality.validationRateSeries'),
    manualReviewRateSeries:
      labels?.manualReviewRateSeries ?? t('accountant.analytics.quality.manualReviewRateSeries'),
    confidenceSeries:
      labels?.confidenceSeries ?? t('accountant.analytics.quality.confidenceSeries'),
  };

  const rates = useMemo(() => qualityRatesToChartRows(months), [months]);
  const volumes = useMemo(() => qualityVolumesToChartRows(months), [months]);
  const buckets = useMemo(
    () => confidenceBucketsToChartRows(confidenceDistribution),
    [confidenceDistribution],
  );
  const hasData = hasQualityChartData(months) || buckets.some((b) => b.value > 0);

  if (loading && months.length === 0 && !error) {
    return <AnalyticsLoadingState cards={4} />;
  }

  if (error) {
    return (
      <AnalyticsErrorState
        title={titleKeys?.errorTitle ?? t('accountant.analytics.quality.errorTitle')}
        message={error}
        onRetry={onRetry}
        retryLabel={t('common.retry')}
      />
    );
  }

  if (!hasData) {
    return (
      <AnalyticsEmptyState
        title={titleKeys?.emptyTitle ?? t('accountant.analytics.quality.emptyTitle')}
        description={
          titleKeys?.emptyDescription ?? t('accountant.analytics.quality.emptyDescription')
        }
      />
    );
  }

  return (
    <>
      <AnalyticsStatGrid>
        <AnalyticsStatCard
          label={L.documentsProcessed}
          value={totals?.documents_processed ?? 0}
        />
        <AnalyticsStatCard
          label={L.extractionSuccessRate}
          value={formatRate(totals?.extraction_success_rate)}
        />
        <AnalyticsStatCard
          label={L.validationSuccessRate}
          value={formatRate(totals?.validation_success_rate)}
        />
        <AnalyticsStatCard
          label={L.averageConfidence}
          value={formatConfidence(totals?.average_confidence)}
        />
        <AnalyticsStatCard
          label={L.manualReviewRate}
          value={formatRate(totals?.manual_review_rate)}
        />
        <AnalyticsStatCard label={L.failedDocuments} value={totals?.failed_documents ?? 0} />
      </AnalyticsStatGrid>

      {rates.length > 0 ? (
        <LineChartCard
          title={L.ratesByMonthTitle}
          data={rates}
          xKey="period"
          yLabel="%"
          series={[
            {
              dataKey: 'extractionSuccessRate',
              name: L.extractionRateSeries,
              color: ANALYTICS_CHART_COLORS.primary,
            },
            {
              dataKey: 'validationSuccessRate',
              name: L.validationRateSeries,
              color: ANALYTICS_CHART_COLORS.secondary,
            },
            {
              dataKey: 'manualReviewRate',
              name: L.manualReviewRateSeries,
              color: ANALYTICS_CHART_COLORS.warning,
            },
            {
              dataKey: 'averageConfidence',
              name: L.confidenceSeries,
              color: ANALYTICS_CHART_COLORS.danger,
            },
          ]}
        />
      ) : null}

      {volumes.length > 0 ? (
        <BarChartCard
          title={L.volumesByMonthTitle}
          data={volumes}
          xKey="period"
          series={[
            {
              dataKey: 'ocrSuccess',
              name: L.ocrSuccess,
              color: ANALYTICS_CHART_COLORS.secondary,
              stackId: 'ocr',
            },
            {
              dataKey: 'ocrFailed',
              name: L.ocrFailed,
              color: ANALYTICS_CHART_COLORS.danger,
              stackId: 'ocr',
            },
            {
              dataKey: 'manualReview',
              name: L.manualReview,
              color: ANALYTICS_CHART_COLORS.warning,
            },
            {
              dataKey: 'failedDocuments',
              name: L.failedDocuments,
              color: ANALYTICS_CHART_COLORS.primary,
            },
          ]}
        />
      ) : null}

      {buckets.some((b) => b.value > 0) ? (
        <DonutChartCard title={L.confidenceDistributionTitle} data={buckets} />
      ) : null}
    </>
  );
}
