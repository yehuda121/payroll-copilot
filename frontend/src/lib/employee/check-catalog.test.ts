import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { buildCheckCatalogRows } from './check-catalog';
import type { GuestValidationReport } from '../../types/validation-report';

const t = ((key: string) => key) as TFunction;

describe('buildCheckCatalogRows', () => {
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
        { rule_id: 'employee.name.match', outcome: 'skipped', skip_reason: 'employee_not_identified' },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    const nid = rows.find((row) => row.ruleId === 'employee.national_id.match');
    const name = rows.find((row) => row.ruleId === 'employee.name.match');
    expect(nid?.status).toBe('passed');
    expect(name?.status).toBe('not_run');
    expect(name?.skipReasonKey).toBe('employee_not_identified');
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

  it('uses generic Not run when skip reason is unknown', () => {
    const report = {
      findings: [],
      ruleOutcomes: [
        { rule_id: 'legal.overtime.daily_limit', outcome: 'skipped', skip_reason: 'internal_xyz' },
      ],
    } as unknown as GuestValidationReport;
    const rows = buildCheckCatalogRows(report, t, 'law_checks');
    const row = rows.find((item) => item.ruleId === 'legal.overtime.daily_limit');
    expect(row?.status).toBe('not_run');
    expect(row?.skipReasonKey).toBeNull();
  });
});
