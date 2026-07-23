import { describe, expect, it } from 'vitest';
import {
  confidenceBucketsToChartRows,
  confidenceToChartRows,
  errorBucketsToChartRows,
  hasQualityChartData,
  hasSalaryChartData,
  outcomesToChartRows,
  periodLabel,
  qualityRatesToChartRows,
  qualityVolumesToChartRows,
  salaryMonthsToChartRows,
  toNumberOrNull,
  validationFailuresToChartRows,
} from './chart-series';

describe('analytics chart-series mappers', () => {
  it('converts decimal-like salary values without inventing amounts', () => {
    expect(toNumberOrNull('12000.50')).toBe(12000.5);
    expect(toNumberOrNull(null)).toBeNull();
    expect(toNumberOrNull('')).toBeNull();
    expect(periodLabel(2026, 3)).toBe('2026-03');
  });

  it('maps salary months for charts', () => {
    const rows = salaryMonthsToChartRows([
      {
        period_year: 2026,
        period_month: 1,
        net_salary: '8000',
        gross_salary: 10000,
        currency: 'ILS',
        document_id: null,
        extraction_id: null,
      },
    ]);
    expect(rows).toEqual([
      { period: '2026-01', month: 1, net: 8000, gross: 10000 },
    ]);
    expect(hasSalaryChartData(rows)).toBe(true);
    expect(hasSalaryChartData([])).toBe(false);
  });

  it('maps org outcome and failure series', () => {
    expect(
      outcomesToChartRows([
        {
          period_year: 2026,
          period_month: 2,
          documents_processed: 5,
          success: 2,
          review_required: 2,
          failed: 1,
        },
      ]),
    ).toEqual([
      {
        period: '2026-02',
        processed: 5,
        success: 2,
        reviewRequired: 2,
        failed: 1,
      },
    ]);

    expect(
      validationFailuresToChartRows([
        {
          period_year: 2026,
          period_month: 2,
          failure_count: 3,
          runs_with_failures: 1,
        },
      ]),
    ).toEqual([{ period: '2026-02', failures: 3, runs: 1 }]);
  });

  it('maps error buckets and confidence percent', () => {
    expect(
      errorBucketsToChartRows([{ key: 'minimum_wage', count: 4, category: 'legal' }]),
    ).toEqual([{ name: 'minimum_wage', value: 4, category: 'legal' }]);

    expect(
      confidenceToChartRows([
        {
          period_year: 2026,
          period_month: 4,
          average_confidence: 0.8,
          sample_count: 2,
        },
      ]),
    ).toEqual([{ period: '2026-04', confidence: 80, samples: 2 }]);
  });

  it('maps quality rates, volumes, and confidence buckets', () => {
    const point = {
      period_year: 2026,
      period_month: 5,
      documents_processed: 10,
      extraction_attempted: 10,
      extraction_success: 8,
      extraction_success_rate: 0.8,
      ocr_attempted: 10,
      ocr_success: 9,
      ocr_failed: 1,
      validation_runs: 8,
      validation_pass: 6,
      validation_success_rate: 0.75,
      average_confidence: 0.88,
      confidence_sample_count: 8,
      manual_review: 2,
      manual_review_rate: 0.2,
      failed_documents: 1,
    };
    expect(qualityRatesToChartRows([point])).toEqual([
      {
        period: '2026-05',
        extractionSuccessRate: 80,
        validationSuccessRate: 75,
        manualReviewRate: 20,
        averageConfidence: 88,
      },
    ]);
    expect(qualityVolumesToChartRows([point])[0]).toMatchObject({
      period: '2026-05',
      ocrSuccess: 9,
      ocrFailed: 1,
      manualReview: 2,
      failedDocuments: 1,
    });
    expect(
      confidenceBucketsToChartRows([
        { label: '0.85-1.00', min_inclusive: 0.85, max_exclusive: 1.0001, count: 4 },
      ]),
    ).toEqual([{ name: '0.85-1.00', value: 4, category: null }]);
    expect(hasQualityChartData([point])).toBe(true);
    expect(hasQualityChartData([])).toBe(false);
  });
});
