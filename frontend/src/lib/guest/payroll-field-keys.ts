/**
 * Canonical payroll field identifiers (internal only).
 * Display labels always go through i18n: t(`payroll.fields.${key}`).
 */
export const CANONICAL_PAYROLL_FIELD_KEYS = [
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
  'national_id',
  'total_deductions',
  'employer_name',
  'employer_id',
  'employer_address',
  'employment_start_date',
  'seniority_years',
  'employment_scope',
  'salary_calculation_basis',
  'amount_paid',
  'bank_name',
  'bank_branch',
  'bank_account',
  'minimum_wage_monthly',
  'minimum_wage_hourly',
] as const;

export type CanonicalPayrollFieldKey = (typeof CANONICAL_PAYROLL_FIELD_KEYS)[number];

const CANONICAL_SET = new Set<string>(CANONICAL_PAYROLL_FIELD_KEYS);

export function isCanonicalPayrollFieldKey(key: string): key is CanonicalPayrollFieldKey {
  return CANONICAL_SET.has(key.trim());
}
