import { describe, expect, it } from 'vitest';
import {
  confidenceToChartRows,
  errorBucketsToChartRows,
  hasSalaryChartData,
  outcomesToChartRows,
  periodLabel,
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
});
