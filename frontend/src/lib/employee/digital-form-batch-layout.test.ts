import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  buildDigitalFormSections,
  digitalFormHasSecondaryFields,
  digitalFormNeedsShowMore,
  INITIAL_DIGITAL_FORM_VISIBLE_COUNT,
  orderDigitalFormFieldsForDisplay,
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

  it('orders name, national id, employee number, and payroll period first when present', () => {
    const sections = buildDigitalFormSections(
      [
        field('gross_salary', 12000),
        field('employee_number', '5'),
        field('pay_period', '01/07/2026'),
        field('national_id', '123456782'),
        field('employee_name', 'Dana'),
        field('net_salary', 9000),
      ],
      {},
      t,
      'en',
      { audience: 'accountant' },
    );
    const ordered = orderDigitalFormFieldsForDisplay(
      sections.flatMap((section) => section.fields),
    );
    expect(ordered.slice(0, 4).map((row) => row.key)).toEqual([
      'employee_name',
      'national_id',
      'employee_number',
      'pay_period',
    ]);
    expect(ordered.map((row) => row.key)).toContain('gross_salary');
  });

  it('needs Show more only when more than the initial visible field count', () => {
    expect(digitalFormNeedsShowMore(INITIAL_DIGITAL_FORM_VISIBLE_COUNT)).toBe(false);
    expect(digitalFormNeedsShowMore(INITIAL_DIGITAL_FORM_VISIBLE_COUNT + 1)).toBe(true);

    const fields = [
      field('employee_name', 'Dana'),
      field('national_id', '123456782'),
      field('gross_salary', 12000),
      field('vacation_balance', 5),
    ];
    expect(digitalFormHasSecondaryFields(fields, {}, t, 'en', { audience: 'accountant' })).toBe(true);
  });
});
