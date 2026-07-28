import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsDashboardLayout,
  AnalyticsYearFilter,
  QualityAnalyticsPanel,
} from '../../features/analytics';
import { useAdminQualityAnalytics } from '../../hooks/useAdminQualityAnalytics';
import './admin-ai.css';

export function AdminQualityAnalyticsPage() {
  const { t } = useTranslation();
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, loading, error, reload } = useAdminQualityAnalytics(year);

  return (
    <PortalPage title={t('admin.quality.title')} description={t('admin.quality.description')}>
      <AnalyticsDashboardLayout
        toolbar={
          <AnalyticsYearFilter
            label={t('admin.quality.year')}
            year={year}
            years={data?.available_years ?? [year]}
            onChange={setYear}
            disabled={loading}
          />
        }
      >
        {data && data.organizations_count > 0 ? (
          <p className="analytics-stat-card" style={{ margin: '0 0 1rem' }}>
            <span>{t('admin.quality.organizationsCovered')}</span>
            <strong>{data.organizations_count}</strong>
          </p>
        ) : null}
        <section className="admin-dashboard-section">
          <header className="admin-dashboard-section__header">
            <h2>{t('admin.quality.sectionTrends')}</h2>
            <p>{t('admin.quality.sectionTrendsDesc')}</p>
          </header>
          <QualityAnalyticsPanel
            months={data?.months ?? []}
            confidenceDistribution={data?.confidence_distribution ?? []}
            totals={data?.totals}
            loading={loading}
            error={error}
            onRetry={reload}
            titleKeys={{
              errorTitle: t('common.error'),
              emptyTitle: t('admin.dashboard.empty'),
              emptyDescription: t('admin.quality.description'),
            }}
            labels={{
              documentsProcessed: t('admin.quality.documentsProcessed'),
              extractionSuccessRate: t('admin.quality.extractionSuccessRate'),
              validationSuccessRate: t('admin.quality.validationSuccessRate'),
              averageConfidence: t('admin.quality.averageConfidence'),
              manualReviewRate: t('admin.quality.manualReviewRate'),
              failedDocuments: t('admin.quality.failedDocuments'),
              ratesByMonthTitle: t('admin.quality.ratesByMonthTitle'),
              volumesByMonthTitle: t('admin.quality.volumesByMonthTitle'),
              confidenceDistributionTitle: t('admin.quality.confidenceDistributionTitle'),
              ocrSuccess: t('admin.quality.ocrSuccess'),
              ocrFailed: t('admin.quality.ocrFailed'),
              manualReview: t('admin.quality.manualReview'),
              extractionRateSeries: t('admin.quality.extractionRateSeries'),
              validationRateSeries: t('admin.quality.validationRateSeries'),
              manualReviewRateSeries: t('admin.quality.manualReviewRateSeries'),
              confidenceSeries: t('admin.quality.confidenceSeries'),
            }}
          />
        </section>
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
