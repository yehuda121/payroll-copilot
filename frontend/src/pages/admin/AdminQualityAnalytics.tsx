import { useState } from 'react';
import { PortalPage } from '../../components/PortalPage';
import {
  AnalyticsDashboardLayout,
  AnalyticsYearFilter,
  QualityAnalyticsPanel,
} from '../../features/analytics';
import { useAdminQualityAnalytics } from '../../hooks/useAdminQualityAnalytics';

export function AdminQualityAnalyticsPage() {
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, loading, error, reload } = useAdminQualityAnalytics(year);

  return (
    <PortalPage
      title="AI Quality Analytics"
      description="Cross-organization extraction, OCR, validation, and confidence quality metrics by payroll month."
    >
      <AnalyticsDashboardLayout
        toolbar={
          <AnalyticsYearFilter
            label="Payroll year"
            year={year}
            years={data?.available_years ?? [year]}
            onChange={setYear}
            disabled={loading}
          />
        }
      >
        <QualityAnalyticsPanel
          months={data?.months ?? []}
          confidenceDistribution={data?.confidence_distribution ?? []}
          totals={data?.totals}
          loading={loading}
          error={error}
          onRetry={reload}
          titleKeys={{
            errorTitle: 'Unable to load quality analytics',
            emptyTitle: 'No quality analytics yet',
            emptyDescription:
              'Quality metrics appear after payslips are extracted with a payroll period.',
          }}
          labels={{
            documentsProcessed: 'Documents processed',
            extractionSuccessRate: 'Extraction success rate',
            validationSuccessRate: 'Validation success rate',
            averageConfidence: 'Average confidence',
            manualReviewRate: 'Manual review rate',
            failedDocuments: 'Failed documents',
            ratesByMonthTitle: 'Quality rates by payroll month',
            volumesByMonthTitle: 'OCR / review / failures by payroll month',
            confidenceDistributionTitle: 'Confidence distribution',
            ocrSuccess: 'OCR success',
            ocrFailed: 'OCR failed',
            manualReview: 'Manual review',
            extractionRateSeries: 'Extraction success %',
            validationRateSeries: 'Validation success %',
            manualReviewRateSeries: 'Manual review %',
            confidenceSeries: 'Avg confidence %',
          }}
        />
        {data && data.organizations_count > 0 ? (
          <p className="analytics-stat-card" style={{ margin: 0 }}>
            <span>Organizations included</span>
            <strong>{data.organizations_count}</strong>
          </p>
        ) : null}
      </AnalyticsDashboardLayout>
    </PortalPage>
  );
}
