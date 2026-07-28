import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  IMPLEMENTED_LAW_CHECK_RULE_IDS,
  LABOR_LAW_RULE_IDS,
  PRIMARY_LAW_CHECK_RULE_IDS,
  SECONDARY_LAW_CHECK_RULE_IDS,
  buildCheckCatalogRows,
  checkRowStatusVisual,
  partitionLawCheckRows,
  summarizeCheckRows,
  summarizeCoreLaborLawRows,
} from './check-catalog';
import type { GuestValidationReport } from '../../types/validation-report';

const t = ((key: string, opts?: { defaultValue?: string }) =>
  opts?.defaultValue ?? key) as TFunction;

describe('buildCheckCatalogRows', () => {
  it('never displays NOT_READY labor-law placeholders', () => {
    expect(LABOR_LAW_RULE_IDS).toHaveLength(17);
    const report = {
      findings: [],
      ruleOutcomes: LABOR_LAW_RULE_IDS.map((rule_id) => ({
        rule_id,
        outcome: 'not_run',
        reason_code: IMPLEMENTED_LAW_CHECK_RULE_IDS.has(rule_id)
          ? 'NOT_APPLICABLE'
          : 'RULE_NOT_READY',
        message: 'skip',
      })),
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    for (const id of LABOR_LAW_RULE_IDS) {
      if (IMPLEMENTED_LAW_CHECK_RULE_IDS.has(id)) continue;
      expect(rows.find((row) => row.ruleId === id)).toBeFalsy();
    }
  });

  it('includes primary and secondary executable law checks in the raw catalog', () => {
    const report = {
      findings: [],
      ruleOutcomes: [...PRIMARY_LAW_CHECK_RULE_IDS, ...SECONDARY_LAW_CHECK_RULE_IDS].map(
        (rule_id) => ({
          rule_id,
          outcome: 'not_run',
          reason_code: 'NOT_APPLICABLE',
          message: 'N/A',
        }),
      ),
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    expect(rows.map((row) => row.ruleId)).toEqual([
      ...PRIMARY_LAW_CHECK_RULE_IDS,
      ...SECONDARY_LAW_CHECK_RULE_IDS,
    ]);
  });

  it('partitions default view to exactly the three production rules', () => {
    const report = {
      findings: [],
      ruleOutcomes: [...PRIMARY_LAW_CHECK_RULE_IDS, ...SECONDARY_LAW_CHECK_RULE_IDS].map(
        (rule_id) => ({
          rule_id,
          outcome: rule_id === 'legal.minimum_wage' ? 'passed' : 'not_run',
          reason_code: rule_id === 'legal.minimum_wage' ? undefined : 'NOT_APPLICABLE',
          message: rule_id === 'legal.minimum_wage' ? undefined : 'N/A',
        }),
      ),
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    const { primary, secondary } = partitionLawCheckRows(rows);
    expect(primary.map((row) => row.ruleId)).toEqual([...PRIMARY_LAW_CHECK_RULE_IDS]);
    expect(primary).toHaveLength(3);
    expect(secondary.map((row) => row.ruleId)).toEqual([...SECONDARY_LAW_CHECK_RULE_IDS]);
    const core = summarizeCoreLaborLawRows(primary);
    expect(core.total).toBe(3);
    expect(core.executed).toBe(1);
    expect(core.skipped).toBe(2);
  });

  it('shows implemented law checks with Not Run + backend reason when they cannot execute', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        {
          rule_id: 'legal.minimum_wage',
          outcome: 'not_run',
          reason_code: 'MISSING_PAY_PERIOD',
          skip_reason: 'missing_pay_period',
          message: 'Pay period missing',
        },
        {
          rule_id: 'legal.overtime.daily_limit',
          outcome: 'not_run',
          reason_code: 'NOT_APPLICABLE',
          message: 'Not applicable',
        },
        {
          rule_id: 'legal.overtime.weekly_limit',
          outcome: 'not_run',
          reason_code: 'RULE_NOT_READY',
          message: 'Not ready',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    expect(rows.find((row) => row.ruleId === 'legal.overtime.weekly_limit')).toBeFalsy();
    const minWage = rows.find((row) => row.ruleId === 'legal.minimum_wage');
    expect(minWage?.status).toBe('not_run');
    expect(minWage?.explanation).toBe('Pay period missing');
    const overtime = rows.find((row) => row.ruleId === 'legal.overtime.daily_limit');
    expect(overtime?.status).toBe('not_run');
    expect(overtime?.explanation).toBe('Not applicable');
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
        {
          rule_id: 'legal.minimum_wage',
          outcome: 'not_run',
          reason_code: 'MISSING_PAY_PERIOD',
          message: 'Missing period',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'all');
    const summary = summarizeCheckRows(rows);
    expect(summary.passed).toBe(1);
    expect(summary.failed).toBe(1);
    expect(summary.uncertain).toBe(1);
    expect(rows.find((row) => row.ruleId === 'legal.overtime.weekly_limit')).toBeFalsy();
    expect(rows.find((row) => row.ruleId === 'legal.minimum_wage')?.status).toBe('not_run');
    expect(summary.executed).toBe(summary.passed + summary.failed + summary.uncertain);
    expect(summary.total).toBe(summary.executed + summary.not_run);
  });

  it('preserves stable catalog order for primary production law checks', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        {
          rule_id: 'legal.youth.minimum_age',
          outcome: 'not_run',
          reason_code: 'NOT_APPLICABLE',
          message: 'N/A',
        },
        {
          rule_id: 'legal.minimum_wage',
          outcome: 'passed',
        },
        {
          rule_id: 'legal.overtime.daily_limit',
          outcome: 'not_run',
          reason_code: 'NOT_APPLICABLE',
          message: 'N/A',
        },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    const { primary } = partitionLawCheckRows(rows);
    expect(primary.map((row) => row.ruleId)).toEqual([...PRIMARY_LAW_CHECK_RULE_IDS]);
  });
});
