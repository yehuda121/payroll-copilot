/**
 * Pure chart-series mappers for analytics dashboards.
 * Keep business aggregation on the backend; these only reshape DTO fields for Recharts.
 */

import type {
  ConfidenceBucket,
  ConfidenceMonthPoint,
  ErrorTypeBucket,
  OutcomeMonthPoint,
  QualityMonthPoint,
  SalaryMonthPoint,
  ValidationFailureMonthPoint,
} from '../../types/analytics';

export function toNumberOrNull(value: number | string | null | undefined): number | null {
  if (value == null || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function periodLabel(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`;
}

export type SalaryChartRow = {
  period: string;
  month: number;
  net: number | null;
  gross: number | null;
};

export function salaryMonthsToChartRows(months: SalaryMonthPoint[]): SalaryChartRow[] {
  return months.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    month: row.period_month,
    net: toNumberOrNull(row.net_salary),
    gross: toNumberOrNull(row.gross_salary),
  }));
}

export type OutcomeChartRow = {
  period: string;
  processed: number;
  success: number;
  reviewRequired: number;
  failed: number;
};

export function outcomesToChartRows(points: OutcomeMonthPoint[]): OutcomeChartRow[] {
  return points.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    processed: row.documents_processed,
    success: row.success,
    reviewRequired: row.review_required,
    failed: row.failed,
  }));
}

export type FailureChartRow = {
  period: string;
  failures: number;
  runs: number;
};

export function validationFailuresToChartRows(
  points: ValidationFailureMonthPoint[],
): FailureChartRow[] {
  return points.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    failures: row.failure_count,
    runs: row.runs_with_failures,
  }));
}

export type BucketChartRow = {
  name: string;
  value: number;
  category: string | null;
};

export function errorBucketsToChartRows(buckets: ErrorTypeBucket[]): BucketChartRow[] {
  return buckets.map((row) => ({
    name: row.key,
    value: row.count,
    category: row.category,
  }));
}

export type ConfidenceChartRow = {
  period: string;
  confidence: number | null;
  samples: number;
};

export function confidenceToChartRows(points: ConfidenceMonthPoint[]): ConfidenceChartRow[] {
  return points.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    confidence:
      row.average_confidence == null ? null : Number((row.average_confidence * 100).toFixed(1)),
    samples: row.sample_count,
  }));
}

export function hasSalaryChartData(rows: SalaryChartRow[]): boolean {
  return rows.some((row) => row.net != null || row.gross != null);
}

export type QualityRateChartRow = {
  period: string;
  extractionSuccessRate: number | null;
  validationSuccessRate: number | null;
  manualReviewRate: number | null;
  averageConfidence: number | null;
};

export function qualityRatesToChartRows(points: QualityMonthPoint[]): QualityRateChartRow[] {
  return points.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    extractionSuccessRate:
      row.extraction_success_rate == null
        ? null
        : Number((row.extraction_success_rate * 100).toFixed(1)),
    validationSuccessRate:
      row.validation_success_rate == null
        ? null
        : Number((row.validation_success_rate * 100).toFixed(1)),
    manualReviewRate:
      row.manual_review_rate == null ? null : Number((row.manual_review_rate * 100).toFixed(1)),
    averageConfidence:
      row.average_confidence == null ? null : Number((row.average_confidence * 100).toFixed(1)),
  }));
}

export type QualityVolumeChartRow = {
  period: string;
  documentsProcessed: number;
  ocrSuccess: number;
  ocrFailed: number;
  manualReview: number;
  failedDocuments: number;
};

export function qualityVolumesToChartRows(points: QualityMonthPoint[]): QualityVolumeChartRow[] {
  return points.map((row) => ({
    period: periodLabel(row.period_year, row.period_month),
    documentsProcessed: row.documents_processed,
    ocrSuccess: row.ocr_success,
    ocrFailed: row.ocr_failed,
    manualReview: row.manual_review,
    failedDocuments: row.failed_documents,
  }));
}

export function confidenceBucketsToChartRows(buckets: ConfidenceBucket[]): BucketChartRow[] {
  return buckets.map((row) => ({
    name: row.label,
    value: row.count,
    category: null,
  }));
}

export function hasQualityChartData(points: QualityMonthPoint[]): boolean {
  return points.some(
    (row) =>
      row.documents_processed > 0 ||
      row.extraction_attempted > 0 ||
      row.validation_runs > 0 ||
      row.confidence_sample_count > 0,
  );
}
