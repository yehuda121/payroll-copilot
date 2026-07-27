import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  LABOR_LAW_RULE_IDS,
  buildCheckCatalogRows,
  checkRowStatusVisual,
  summarizeCheckRows,
} from './check-catalog';
import type { GuestValidationReport } from '../../types/validation-report';

const t = ((key: string, opts?: { defaultValue?: string }) =>
  opts?.defaultValue ?? key) as TFunction;

describe('buildCheckCatalogRows', () => {
  it('renders all 17 labor-law catalog checks', () => {
    expect(LABOR_LAW_RULE_IDS).toHaveLength(17);
    const report = {
      findings: [],
      ruleOutcomes: LABOR_LAW_RULE_IDS.map((rule_id) => ({
        rule_id,
        outcome: 'not_run',
        reason_code: 'RULE_NOT_READY',
        message: 'Not ready',
      })),
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    for (const id of LABOR_LAW_RULE_IDS) {
      expect(rows.find((row) => row.ruleId === id)).toBeTruthy();
    }
  });

  it('does not fabricate PASS without authoritative outcomes', () => {
    const report = {
      findings: [],
      ruleOutcomes: [],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.status === 'not_run')).toBe(true);
  });

  it('shows PASS only when rule_outcomes.passed', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        { rule_id: 'employee.national_id.match', outcome: 'passed' },
        {
          rule_id: 'employee.name.match',
          outcome: 'not_run',
          skip_reason: 'employee_not_identified',
          reason_code: 'EMPLOYEE_NOT_IDENTIFIED',
          message: 'Not identified',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    const nid = rows.find((row) => row.ruleId === 'employee.national_id.match');
    const name = rows.find((row) => row.ruleId === 'employee.name.match');
    expect(nid?.status).toBe('passed');
    expect(name?.status).toBe('not_run');
    expect(name?.explanation).toBeTruthy();
  });

  it('keeps failed findings as failed', () => {
    const report = {
      findings: [
        {
          id: 'f1',
          code: 'legal.minimum_wage',
          rule_id: 'legal.minimum_wage',
          severity: 'critical',
          message_key: 'validation.minimum_wage.below_threshold',
          message: '',
          explanation: 'Below threshold',
          expected_value: '30',
          actual_value: '20',
          confidence: 1,
          legal_reference: null,
        },
      ],
      ruleOutcomes: [{ rule_id: 'legal.minimum_wage', outcome: 'failed' }],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    const row = rows.find((item) => item.ruleId === 'legal.minimum_wage');
    expect(row?.status).toBe('failed');
  });

  it('maps uncertain outcomes distinctly', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        {
          rule_id: 'employee.national_id.match',
          outcome: 'uncertain',
          reason_code: 'MISSING_PAYSLIP_DATA',
          message: 'Required payslip data unavailable',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    const row = rows.find((item) => item.ruleId === 'employee.national_id.match');
    expect(row?.status).toBe('uncertain');
  });

  it('keeps NOT_RUN visually neutral and never aria-invalid', () => {
    const visual = checkRowStatusVisual('not_run', t);
    expect(visual.css).toBe('is-not-run');
    expect(visual.css).not.toBe('is-failed');
    expect(visual.css).not.toBe('is-passed');
  });

  it('summarizes explicit outcomes correctly', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        { rule_id: 'employee.national_id.match', outcome: 'passed' },
        { rule_id: 'employee.name.match', outcome: 'failed' },
        { rule_id: 'employee.employee_number.match', outcome: 'uncertain' },
        {
          rule_id: 'legal.overtime.weekly_limit',
          outcome: 'not_run',
          reason_code: 'RULE_NOT_READY',
          message: 'Not ready',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'all');
    const summary = summarizeCheckRows(rows);
    expect(summary.passed).toBe(1);
    expect(summary.failed).toBe(1);
    expect(summary.uncertain).toBe(1);
    expect(summary.not_run).toBeGreaterThanOrEqual(1);
    expect(summary.executed).toBe(summary.passed + summary.failed + summary.uncertain);
    expect(summary.total).toBe(summary.executed + summary.not_run);
  });

  it('preserves stable catalog order', () => {
    const report = {
      findings: [],
      ruleOutcomes: LABOR_LAW_RULE_IDS.map((rule_id) => ({
        rule_id,
        outcome: 'not_run',
        reason_code: 'RULE_NOT_READY',
      })),
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    const lawRows = rows.filter((row) => row.ruleId.startsWith('legal.'));
    expect(lawRows.map((row) => row.ruleId)).toEqual([...LABOR_LAW_RULE_IDS]);
  });
});
