import { describe, expect, it } from 'vitest';
import { buildEmployeeFieldValidationMap } from './field-validation-status';
import type { ExtractedPayslipField, ValidationFinding } from '../../types/api';
import type { GuestValidationReport } from '../../types/validation-report';

function field(key: string, value: unknown, status = 'FOUND'): ExtractedPayslipField {
  return {
    key,
    value,
    confidence: 0.9,
    source_text: null,
    status,
    edited_by_user: false,
  };
}

function finding(partial: Partial<ValidationFinding> & { id: string; rule_id: string }): ValidationFinding {
  return {
    code: partial.code || partial.rule_id,
    severity: partial.severity || 'critical',
    message_key: partial.message_key || partial.rule_id,
    message_params: {},
    expected_value: partial.expected_value ?? null,
    actual_value: partial.actual_value ?? null,
    confidence: partial.confidence ?? 1,
    explanation: partial.explanation ?? null,
    ...partial,
  } as ValidationFinding;
}

describe('buildEmployeeFieldValidationMap', () => {
  it('aggregates explicit bound findings with FAILED precedence', () => {
    const report = {
      findings: [
        finding({
          id: '1',
          rule_id: 'legal.overtime.daily_limit',
          severity: 'critical',
        }),
      ],
      ruleOutcomes: [{ rule_id: 'legal.overtime.daily_limit', outcome: 'failed' }],
    } as GuestValidationReport;

    const map = buildEmployeeFieldValidationMap(
      [field('overtime_hours', 5)],
      report,
    );
    expect(map.overtime_hours.status).toBe('failed');
  });

  it('does not fuzzy-bind unrelated findings to fields', () => {
    const report = {
      findings: [
        finding({
          id: '1',
          rule_id: 'legal.overtime.daily_limit',
          severity: 'critical',
          explanation: 'base_salary mentioned in text only',
        }),
      ],
    } as GuestValidationReport;

    const map = buildEmployeeFieldValidationMap([field('base_salary', 100)], report);
    expect(map.base_salary.status).not.toBe('failed');
  });

  it('marks missing required_on_payslip as uncertain, never failed', () => {
    const map = buildEmployeeFieldValidationMap([field('gross_salary', 1)], null);
    expect(map.employee_name?.neutralKind).toBe('missing_required');
    expect(map.employee_name?.status).toBe('uncertain');
    expect(map.employee_name?.status).not.toBe('failed');
  });

  it('does not treat sanity.required findings as failed', () => {
    const report = {
      findings: [
        finding({
          id: '1',
          rule_id: 'sanity.required.employee_name',
          severity: 'info',
          message_key: 'validation.sanity.required_field_missing',
        }),
      ],
      ruleOutcomes: [{ rule_id: 'sanity.required.employee_name', outcome: 'failed' }],
    } as GuestValidationReport;
    const map = buildEmployeeFieldValidationMap([field('employee_name', null, 'MISSING')], report);
    expect(map.employee_name.status).toBe('uncertain');
    expect(map.employee_name.neutralKind).toBe('missing_required');
  });

  it('marks bound fields passed only when rule_outcomes say passed', () => {
    const report = {
      findings: [],
      ruleOutcomes: [{ rule_id: 'legal.overtime.daily_limit', outcome: 'passed' }],
    } as unknown as GuestValidationReport;
    const map = buildEmployeeFieldValidationMap([field('overtime_hours', 2)], report);
    expect(map.overtime_hours.status).toBe('passed');
  });

  it('does not fabricate PASS from empty findings without outcomes', () => {
    const report = { findings: [] } as unknown as GuestValidationReport;
    const map = buildEmployeeFieldValidationMap([field('overtime_hours', 2)], report);
    expect(map.overtime_hours.status).not.toBe('passed');
  });
});
