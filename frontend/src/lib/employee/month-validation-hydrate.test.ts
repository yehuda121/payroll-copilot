/**
 * Employee month hydration must map persisted rule_outcomes (fixes false 0/8).
 */
import { describe, expect, it } from 'vitest';
import { reportFromMonthDetail } from '../../hooks/useEmployeeMonthWorkspace';
import {
  buildCheckCatalogRows,
  summarizeCheckRows,
} from './check-catalog';
import type { PayrollMonthDetail } from '../../services/employeePortal';

const t = ((key: string) => key) as (key: string, opts?: Record<string, unknown>) => string;

function detailWithOutcomes(): PayrollMonthDetail {
  return {
    year: 2026,
    month: 6,
    payslip: {
      exists: true,
      document_id: 'doc-1',
      original_filename: 'a.pdf',
      uploaded_at: null,
      status: 'processed',
    },
    attendance: {
      exists: false,
      document_id: null,
      original_filename: null,
      uploaded_at: null,
      status: null,
    },
    missing_documents: [],
    presentation_status: 'passed',
    actions: {
      can_upload_payslip: true,
      can_upload_attendance: true,
      can_run_validation: true,
    },
    latest_validation: {
      exists: true,
      validation_run_id: 'run-1',
      status: 'completed',
      overall_result: 'pass',
      confidence: 0.9,
      completed_at: '2026-06-01T00:00:00Z',
      findings_count: 0,
      highest_severity: null,
      scope: [],
      findings: [
        {
          id: 'f1',
          code: 'validation.employee.national_id.mismatch',
          rule_id: 'employee.national_id.match',
          severity: 'critical',
          message_key: 'validation.employee.national_id.mismatch',
          message_params: {},
          expected_value: null,
          actual_value: null,
        },
      ],
      rule_outcomes: [
        {
          rule_id: 'employee.national_id.match',
          outcome: 'failed',
          reason_code: null,
          skip_reason: null,
          message: null,
        },
        {
          rule_id: 'employee.name.match',
          outcome: 'uncertain',
          reason_code: 'MISSING_PAYSLIP_DATA',
          skip_reason: null,
          message: 'missing',
        },
        {
          rule_id: 'employee.employee_number.match',
          outcome: 'passed',
        },
        {
          rule_id: 'employee.employment_type.match',
          outcome: 'not_run',
          reason_code: 'NOT_APPLICABLE',
        },
        {
          rule_id: 'employee.pay_period.match',
          outcome: 'passed',
        },
        {
          rule_id: 'contract.employment_commencement_date.match',
          outcome: 'not_run',
          reason_code: 'NO_CONFIRMED_CONTRACT',
        },
        {
          rule_id: 'contract.salary_basis.match',
          outcome: 'not_run',
          reason_code: 'NO_CONFIRMED_CONTRACT',
        },
        {
          rule_id: 'contract.hourly_rate.match',
          outcome: 'not_run',
          reason_code: 'NO_CONFIRMED_CONTRACT',
        },
        {
          rule_id: 'legal.minimum_wage',
          outcome: 'passed',
        },
      ],
      manual_approvals: [],
    },
  };
}

describe('reportFromMonthDetail rule_outcomes', () => {
  it('maps persisted rule_outcomes and rule_id on findings', () => {
    const report = reportFromMonthDetail(detailWithOutcomes(), t);
    expect(report).not.toBeNull();
    expect(report!.ruleOutcomes?.length).toBeGreaterThan(0);
    expect(report!.findings[0].rule_id).toBe('employee.national_id.match');
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    const summary = summarizeCheckRows(rows);
    expect(summary.total).toBe(8);
    expect(summary.executed).toBeGreaterThan(0);
    expect(summary.executed).not.toBe(0);
    expect(summary.failed).toBe(1);
    expect(summary.uncertain).toBe(1);
    expect(summary.passed).toBe(2);
  });

  it('keeps legal outcomes after hydrate (not only employee checks)', () => {
    const report = reportFromMonthDetail(detailWithOutcomes(), t);
    const law = buildCheckCatalogRows(report, t, 'law_checks');
    const minWage = law.find((r) => r.ruleId === 'legal.minimum_wage');
    expect(minWage?.status).toBe('passed');
  });

  it('does not fabricate PASS when outcomes are absent', () => {
    const bare = detailWithOutcomes();
    bare.latest_validation.rule_outcomes = [];
    bare.latest_validation.findings = [];
    const report = reportFromMonthDetail(bare, t);
    const rows = buildCheckCatalogRows(report, t, 'employee_checks');
    const summary = summarizeCheckRows(rows);
    expect(summary.executed).toBe(0);
    expect(summary.passed).toBe(0);
  });
});
