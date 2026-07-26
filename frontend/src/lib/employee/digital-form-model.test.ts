import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import { buildDigitalFormSections } from './digital-form-model';
import type { ExtractedPayslipField } from '../../types/api';

const t = ((key: string) => key) as TFunction;

function field(key: string, value: unknown): ExtractedPayslipField {
  return {
    key,
    value,
    confidence: 0.9,
    source_text: null,
    status: 'FOUND',
    edited_by_user: false,
  };
}

describe('buildDigitalFormSections', () => {
  it('orders Required before Expected and injects missing required empties', () => {
    const sections = buildDigitalFormSections(
      [field('gross_salary', 10000), field('vacation_balance', 5)],
      {},
      t,
      'en',
      { audience: 'employee' },
    );
    expect(sections.map((s) => s.id)).toEqual(['required', 'expected']);
    const requiredKeys = sections[0].fields.map((f) => f.key);
    expect(requiredKeys[0]).toBe('employee_name');
    expect(sections[0].fields.some((f) => f.key === 'national_id' && f.missingRequired)).toBe(
      true,
    );
    expect(sections[0].fields.some((f) => f.key === 'employer_name' && f.missingRequired)).toBe(
      true,
    );
    expect(sections[0].fields.some((f) => f.key === 'gross_salary' && !f.missingRequired)).toBe(
      true,
    );
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
