import type { TFunction } from 'i18next';
import type { ExtractedPayslipField } from '../../types/api';

export type ExtractionField = {
  key: string;
  label: string;
  displayValue: string;
  rawValue: unknown;
  status: string;
  confidenceLabel: string | null;
  sourceText: string | null;
  editedByUser: boolean;
};

const REVIEW_FIELD_ORDER = [
  'employee_name',
  'employee_id',
  'employee_number',
  'pay_period',
  'employment_type',
  'department',
  'hourly_rate',
  'base_salary',
  'travel_expenses',
  'regular_hours',
  'overtime_hours',
  'gross_salary',
  'income_tax',
  'national_insurance',
  'health_tax',
  'pension_employee',
  'pension_employer',
  'severance',
  'training_fund',
  'net_salary',
  'vacation_balance',
  'sick_leave_balance',
  'payment_method',
  'messages',
] as const;

const LABEL_KEYS: Record<string, string> = {
  employee_name: 'validate.fieldEmployeeName',
  employee_id: 'validate.fieldEmployeeId',
  employee_number: 'validate.fieldEmployeeNumber',
  pay_period: 'validate.fieldPayPeriod',
  employment_type: 'validate.fieldEmploymentType',
  department: 'validate.fieldDepartment',
  hourly_rate: 'validate.fieldHourlyRate',
  base_salary: 'validate.fieldBaseSalary',
  travel_expenses: 'validate.fieldTravel',
  regular_hours: 'validate.fieldWorkHours',
  overtime_hours: 'validate.fieldOvertime',
  gross_salary: 'validate.fieldGrossSalary',
  income_tax: 'validate.fieldTax',
  national_insurance: 'validate.fieldNationalInsurance',
  health_tax: 'validate.fieldHealthTax',
  pension_employee: 'validate.fieldPensionEmployee',
  pension_employer: 'validate.fieldPensionEmployer',
  severance: 'validate.fieldSeverance',
  training_fund: 'validate.fieldTrainingFund',
  net_salary: 'validate.fieldNetSalary',
  vacation_balance: 'validate.fieldVacationBalance',
  sick_leave_balance: 'validate.fieldSickLeaveBalance',
  payment_method: 'validate.fieldPaymentMethod',
  messages: 'validate.fieldMessages',
};

function formatValue(value: unknown, status: string, t: TFunction): string {
  if (status === 'MISSING' || value === null || value === undefined || value === '') {
    return t('validate.fieldMissing');
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return t('validate.fieldUnableToRead');
    }
  }
  return String(value);
}

function confidenceLabel(confidence: number | null | undefined, t: TFunction): string | null {
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) {
    return t('validate.confidenceUnavailable');
  }
  return `${Math.round(confidence * 100)}%`;
}

function fieldLabel(key: string, t: TFunction): string {
  const i18nKey = LABEL_KEYS[key];
  if (i18nKey) {
    return t(i18nKey);
  }
  return key.replaceAll('_', ' ');
}

/** Map parser fields into review rows. Never invent values or confidence. */
export function buildExtractionReviewFields(
  fields: ExtractedPayslipField[] | null | undefined,
  t: TFunction,
): ExtractionField[] {
  const byKey = new Map((fields ?? []).map((field) => [field.key, field]));

  return REVIEW_FIELD_ORDER.map((key) => {
    const field = byKey.get(key);
    const status = (field?.status || 'MISSING').toUpperCase();
    const displayValue =
      status === 'UNCERTAIN' && (field?.value === null || field?.value === undefined || field?.value === '')
        ? t('validate.fieldUnableToRead')
        : formatValue(field?.value, status, t);

    return {
      key,
      label: fieldLabel(key, t),
      displayValue,
      rawValue: field?.value ?? null,
      status,
      confidenceLabel: confidenceLabel(field?.confidence ?? null, t),
      sourceText: field?.source_text ?? null,
      editedByUser: Boolean(field?.edited_by_user),
    };
  });
}

export function isImageFile(file: File | undefined): boolean {
  if (!file) return false;
  const name = file.name.toLowerCase();
  return (
    file.type.startsWith('image/') ||
    name.endsWith('.png') ||
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg')
  );
}
