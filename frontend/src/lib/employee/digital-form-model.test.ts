import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { buildDigitalFormSections } from './digital-form-model';
import type { ExtractedPayslipField } from '../../types/api';

const t = ((key: string) => key) as TFunction;

function field(
  key: string,
  value: unknown,
  status: ExtractedPayslipField['status'] = 'FOUND',
): ExtractedPayslipField {
  return {
    key,
    value,
    confidence: 0.9,
    source_text: null,
    status,
    edited_by_user: false,
  };
}

describe('buildDigitalFormSections', () => {
  it('always shows required_on_payslip slots and hides missing optional fields', () => {
    const sections = buildDigitalFormSections(
      [field('gross_salary', 10000), field('vacation_balance', 5), field('employer_name', null, 'MISSING')],
      {},
      t,
      'en',
      { audience: 'employee' },
    );
    expect(sections.map((s) => s.id)).toEqual(['required', 'expected']);
    const requiredKeys = sections[0].fields.map((f) => f.key);
    expect(requiredKeys).toEqual(['employee_name', 'national_id']);
    expect(sections[0].fields.every((f) => f.missingRequired)).toBe(true);

    const expected = sections.find((s) => s.id === 'expected')!;
    expect(expected.fields.map((f) => f.key).sort()).toEqual(['gross_salary', 'vacation_balance']);
    expect(expected.fields.some((f) => f.key === 'employer_name')).toBe(false);
    expect(expected.fields.some((f) => f.key === 'net_salary')).toBe(false);
  });

  it('hides Other for employee but shows for accountant', () => {
    const fields = [field('gross_salary', 1), field('weird_custom_line', 'x')];
    const employee = buildDigitalFormSections(fields, {}, t, 'en', { audience: 'employee' });
    expect(employee.some((s) => s.id === 'other')).toBe(false);

    const accountant = buildDigitalFormSections(fields, {}, t, 'en', { audience: 'accountant' });
    expect(accountant.some((s) => s.id === 'other')).toBe(true);
    expect(accountant.find((s) => s.id === 'other')?.fields.some((f) => f.key === 'weird_custom_line')).toBe(
      true,
    );
  });

  it('treats dedicated national_id as the required National ID slot', () => {
    const sections = buildDigitalFormSections(
      [field('national_id', '123456782'), field('gross_salary', 1)],
      {},
      t,
      'en',
      { audience: 'employee' },
    );
    const required = sections.find((s) => s.id === 'required')!;
    expect(required.fields.some((f) => f.key === 'national_id' && !f.missingRequired)).toBe(true);
    expect(required.fields.some((f) => f.key === 'employee_id')).toBe(false);
  });

  it('legacy employee_id with Israeli ID digits satisfies national_id without inventing values', () => {
    const sections = buildDigitalFormSections(
      [field('employee_id', '313366783'), field('gross_salary', 1)],
      {},
      t,
      'en',
      { audience: 'employee' },
    );
    const required = sections.find((s) => s.id === 'required')!;
    expect(required.fields.some((f) => f.key === 'national_id' && !f.missingRequired)).toBe(true);
  });

  it('does not treat EMP-style employee_id as National ID', () => {
    const sections = buildDigitalFormSections(
      [field('employee_id', 'EMP-99'), field('gross_salary', 1)],
      {},
      t,
      'en',
      { audience: 'employee' },
    );
    const required = sections.find((s) => s.id === 'required')!;
    expect(required.fields.some((f) => f.key === 'national_id' && f.missingRequired)).toBe(true);
  });
});
