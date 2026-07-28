import { describe, expect, it } from 'vitest';
import {
  BACKEND_PAYSLIP_CANONICAL_EXTRA_KEYS,
  BACKEND_PAYSLIP_FIELD_KEYS,
  looksLikeNationalIdDigits,
  registrySnapshotForSync,
  requiredOnPayslipKeys,
  requirementCategoryForKey,
} from './payslip-field-registry';

describe('payslip-field-registry', () => {
  it('uses national_id as required National ID, not employee_id', () => {
    const required = requiredOnPayslipKeys();
    expect(required).toEqual(['employee_name', 'national_id', 'pay_period']);
    expect(required).not.toContain('employee_id');
    expect(requirementCategoryForKey('employee_id')).toBe('expected');
  });

  it('registers newly approved canonical concepts', () => {
    for (const key of [
      'employer_name',
      'amount_paid',
      'minimum_wage_monthly',
      'bank_account',
      'employment_scope',
      'salary_calculation_basis',
    ]) {
      expect(BACKEND_PAYSLIP_CANONICAL_EXTRA_KEYS).toContain(key);
      expect(requirementCategoryForKey(key)).toMatch(/required|expected/);
    }
  });

  it('limits required_on_payslip presentation slots to identity + period', () => {
    expect(requiredOnPayslipKeys()).toEqual(['employee_name', 'national_id', 'pay_period']);
    expect(requirementCategoryForKey('amount_paid')).toBe('expected');
    expect(requirementCategoryForKey('net_salary')).toBe('expected');
  });

  it('covers backend PAYSLIP_FIELD_KEYS', () => {
    for (const key of BACKEND_PAYSLIP_FIELD_KEYS) {
      expect(requirementCategoryForKey(key)).toMatch(/required|expected|other/);
    }
  });

  it('exposes a stable sync snapshot with corrected NID semantics', () => {
    const snap = registrySnapshotForSync();
    expect(snap.national_id.required_on_payslip).toBe(true);
    expect(snap.employee_name.required_on_payslip).toBe(true);
    expect(snap.employee_id.required_on_payslip).toBe(false);
    expect(snap.employer_name.required_on_payslip).toBe(false);
    expect(snap.employer_name.section).toBe('employer');
  });

  it('detects Israeli ID-shaped legacy employee_id values only', () => {
    expect(looksLikeNationalIdDigits('313366783')).toBe(true);
    expect(looksLikeNationalIdDigits('EMP-99')).toBe(false);
  });
});
