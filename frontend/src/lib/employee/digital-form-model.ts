/**
 * Digital form view-model.
 * Currently renders as one continuous form; section metadata is kept so
 * future grouping can be enabled without rewriting the form.
 */

import type { TFunction } from 'i18next';
import type { ExtractedPayslipField } from '../../types/api';
import { filterMeaningfulReviewFields } from '../guest/extraction-review';
import { isCanonicalPayrollFieldKey } from '../guest/payroll-field-keys';
import {
  detectEmployeeFieldType,
  fieldSpansColumns,
  formatFieldPreview,
  serializeFieldValue,
  type EmployeeFieldType,
} from './field-types';

export type DigitalFormFieldModel = {
  key: string;
  label: string;
  type: EmployeeFieldType;
  /** Serialized editable value */
  value: string;
  rawValue: unknown;
  preview: string;
  columnSpan: 1 | 2;
  /** Reserved for future section grouping */
  sectionId: string;
};

export type DigitalFormSectionModel = {
  id: string;
  /** When null, UI renders without a section heading (continuous form). */
  titleKey: string | null;
  fields: DigitalFormFieldModel[];
};

function fieldLabel(key: string, t: TFunction): string {
  if (isCanonicalPayrollFieldKey(key)) {
    return t(`payroll.fields.${key}`);
  }
  return t(`validate.field.${key}`, { defaultValue: key });
}

function inferSectionId(key: string): string {
  // Stable future hooks — not shown in UI yet.
  if (['employee_name', 'employee_id', 'employee_number', 'national_id', 'department', 'employment_type'].includes(key)) {
    return 'identity';
  }
  if (['pay_period', 'payment_method'].includes(key)) return 'period';
  if (
    ['base_salary', 'gross_salary', 'net_salary', 'hourly_rate', 'travel_expenses', 'regular_hours', 'overtime_hours'].includes(
      key,
    )
  ) {
    return 'earnings';
  }
  if (
    [
      'income_tax',
      'national_insurance',
      'health_tax',
      'pension_employee',
      'pension_employer',
      'severance',
      'training_fund',
      'total_deductions',
    ].includes(key)
  ) {
    return 'deductions';
  }
  return 'other';
}

export function buildDigitalFormSections(
  fields: ExtractedPayslipField[] | undefined,
  drafts: Record<string, { value: string }>,
  t: TFunction,
  locale: string,
): DigitalFormSectionModel[] {
  const models: DigitalFormFieldModel[] = filterMeaningfulReviewFields(fields).map((field) => {
    const draft = drafts[field.key];
    // Prefer live draft for editing, but do not keep empty drafts on screen.
    const value = draft?.dirty ? draft.value : (draft?.value ?? serializeFieldValue(field.value));
    if (!value.trim() && !draft?.dirty) {
      return null;
    }
    const type = detectEmployeeFieldType(field.key, draft?.dirty ? value : field.value);
    return {
      key: field.key,
      label: fieldLabel(field.key, t),
      type,
      value,
      rawValue: field.value ?? null,
      preview: formatFieldPreview(value, type, locale),
      columnSpan: fieldSpansColumns(type, value),
      sectionId: inferSectionId(field.key),
    };
  }).filter((model): model is DigitalFormFieldModel => model != null);

  // Continuous form today: one untitled section containing all fields.
  // Future: split by sectionId and set titleKey per group.
  if (models.length === 0) return [];
  return [
    {
      id: 'all',
      titleKey: null,
      fields: models,
    },
  ];
}
