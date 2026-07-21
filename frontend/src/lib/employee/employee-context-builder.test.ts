import { describe, expect, it } from 'vitest';
import type { EmployeeSessionInspectSnapshot } from '../../auth/EmployeeSessionContext';
import type { PayrollMonthDetail, PayrollMonthsResponse } from '../../services/employeePortal';
import { buildEmployeeContext } from './employee-context-builder';

function emptySnapshot(
  overrides: Partial<EmployeeSessionInspectSnapshot> = {},
): EmployeeSessionInspectSnapshot {
  return {
    profile: null,
    payrollMonthsByYear: [],
    payrollMonthDetails: [],
    documentCenter: null,
    documentForms: [],
    validationReports: [],
    ...overrides,
  };
}

function monthDetail(year: number, month: number): PayrollMonthDetail {
  return {
    year,
    month,
    payslip: {
      exists: true,
      document_id: 'doc-1',
      uploaded_at: null,
      status: 'ready',
    },
    attendance: {
      exists: false,
      document_id: null,
      uploaded_at: null,
      status: 'missing',
    },
    latest_validation: {
      exists: false,
      validation_run_id: null,
      status: 'missing',
      confidence: null,
      completed_at: null,
      findings_count: 0,
      highest_severity: null,
      scope: [],
    },
    missing_documents: [],
    presentation_status: 'ready',
    actions: {
      can_upload_payslip: false,
      can_upload_attendance: false,
      can_run_validation: false,
    },
  };
}

describe('buildEmployeeContext', () => {
  it('reports missing profile and known document forms when cache is empty', () => {
    const ctx = buildEmployeeContext(emptySnapshot(), {
      now: () => new Date('2026-07-18T12:00:00.000Z'),
    });

    expect(ctx.builtAt).toBe('2026-07-18T12:00:00.000Z');
    expect(ctx.isAvailable('employee_profile')).toBe(false);
    expect(ctx.getResource('employee_profile')?.status).toBe('missing');
    expect(ctx.isAvailable('document_form:contract')).toBe(false);
    expect(ctx.getResource('document_form:national_id')?.label).toBe('ID Card');
    expect(ctx.availabilitySummary()).toEqual(
      expect.arrayContaining([
        { label: 'Employee Profile', status: 'Missing' },
        { label: 'Employment Contract', status: 'Missing' },
        { label: 'ID Card', status: 'Missing' },
      ]),
    );
  });

  it('exposes loaded profile, month detail, and marks other list months missing', () => {
    const list: PayrollMonthsResponse = {
      year: 2026,
      available_years: [2026],
      months: [
        {
          month: 5,
          payslip: {
            exists: true,
            document_id: 'a',
            uploaded_at: null,
            status: 'ready',
          },
          attendance: {
            exists: false,
            document_id: null,
            uploaded_at: null,
            status: 'missing',
          },
          latest_validation: {
            exists: false,
            validation_run_id: null,
            status: 'missing',
            confidence: null,
            completed_at: null,
            findings_count: 0,
            highest_severity: null,
            scope: [],
          },
          presentation_status: 'ready',
        },
        {
          month: 4,
          payslip: {
            exists: true,
            document_id: 'b',
            uploaded_at: null,
            status: 'ready',
          },
          attendance: {
            exists: false,
            document_id: null,
            uploaded_at: null,
            status: 'missing',
          },
          latest_validation: {
            exists: false,
            validation_run_id: null,
            status: 'missing',
            confidence: null,
            completed_at: null,
            findings_count: 0,
            highest_severity: null,
            scope: [],
          },
          presentation_status: 'ready',
        },
      ],
    };

    const ctx = buildEmployeeContext(
      emptySnapshot({
        profile: {
          employee_id: 'e1',
          employee_number: '100',
          full_name: 'Ada',
          national_id_masked: null,
          organization_id: 'org',
          status: 'active',
        },
        payrollMonthsByYear: [list],
        payrollMonthDetails: [monthDetail(2026, 5)],
        documentForms: [
          {
            document_id: 'id-1',
            extraction_id: 'x',
            extraction_version: 1,
            document_type: 'national_id',
            original_filename: 'id.pdf',
            uploaded_at: null,
            status: 'ready',
            fields: [],
          },
        ],
      }),
    );

    expect(ctx.isAvailable('employee_profile')).toBe(true);
    expect(ctx.isAvailable('payroll_month_detail:2026-05')).toBe(true);
    expect(ctx.isAvailable('payroll_month_detail:2026-04')).toBe(false);
    expect(ctx.getResource('payroll_month_detail:2026-04')?.label).toBe('Payroll Month 2026-04');
    expect(ctx.isAvailable('document_form:national_id')).toBe(true);
    expect(ctx.isAvailable('document_form:contract')).toBe(false);
    expect(ctx.listByKind('payroll_month_detail')).toHaveLength(2);
  });

  it('never invents data when nothing is cached', () => {
    const ctx = buildEmployeeContext(emptySnapshot());
    expect(ctx.profile).toBeNull();
    expect(ctx.payrollMonthDetails).toEqual([]);
    expect(ctx.documentForms).toEqual([]);
    expect(ctx.validationReports).toEqual([]);
  });
});
