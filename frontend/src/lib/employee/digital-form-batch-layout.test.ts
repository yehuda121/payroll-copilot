import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  buildDigitalFormSections,
  digitalFormHasSecondaryFields,
} from './digital-form-model';
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

describe('Digital payslip form sections for accountant batch review', () => {
  it('groups by registry sections without Required/Expected/Other classification titles', () => {
    const sections = buildDigitalFormSections(
      [
        field('employee_name', 'Dana'),
        field('national_id', '123456782'),
        field('gross_salary', 12000),
      ],
      {},
      t,
      'en',
      { audience: 'accountant' },
    );

    expect(sections.length).toBeGreaterThan(0);
    expect(sections.every((section) => section.titleKey?.startsWith('employee.digitalForm.sections.'))).toBe(
      true,
    );
    expect(sections.some((section) => section.titleKey === 'employee.digitalForm.sectionRequired')).toBe(
      false,
    );
    expect(sections.some((section) => section.titleKey === 'employee.digitalForm.sectionExpected')).toBe(
      false,
    );
    const keys = sections.flatMap((section) => section.fields.map((row) => row.key));
    expect(keys).toContain('employee_name');
    expect(keys).toContain('national_id');
    expect(keys).toContain('gross_salary');
  });

  it('supports primary-only view and secondary reveal for Show more', () => {
    const fields = [
      field('employee_name', 'Dana'),
      field('national_id', '123456782'),
      field('gross_salary', 12000),
      field('vacation_balance', 5),
    ];
    const primary = buildDigitalFormSections(fields, {}, t, 'en', {
      audience: 'accountant',
      requirementCategories: ['required'],
    });
    const primaryKeys = primary.flatMap((section) => section.fields.map((row) => row.key));
    expect(primaryKeys).toContain('employee_name');
    expect(primaryKeys).not.toContain('vacation_balance');

    expect(digitalFormHasSecondaryFields(fields, {}, t, 'en', { audience: 'accountant' })).toBe(true);

    const all = buildDigitalFormSections(fields, {}, t, 'en', { audience: 'accountant' });
    const allKeys = all.flatMap((section) => section.fields.map((row) => row.key));
    expect(allKeys).toContain('vacation_balance');
  });
});
