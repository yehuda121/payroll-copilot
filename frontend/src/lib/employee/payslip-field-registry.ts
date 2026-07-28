/**
 * Frontend mirror of backend payslip_field_registry.
 * Keep in sync with:
 *   backend/.../application/services/payslip_field_registry.py
 *
 * Presentation metadata only — does not change extraction or persistence gates.
 */

export type FieldRequirementCategory = 'required' | 'expected' | 'other';

export type PayslipFieldSection =
  | 'identity'
  | 'employer'
  | 'period'
  | 'earnings'
  | 'deductions'
  | 'payment'
  | 'other';

export type PayslipFieldDefinition = {
  canonical_key: string;
  label_i18n_key: string;
  section: PayslipFieldSection;
  display_order: number;
  requirement_category: FieldRequirementCategory;
  editable: boolean;
  /** Presentation: show empty when missing. Not a persistence blocker. */
  required_on_payslip: boolean;
  /** Reserved metadata — existing gates remain the persistence SoT. */
  required_for_persistence: boolean;
};

type DefInput = {
  key: string;
  section: PayslipFieldSection;
  order: number;
  category: FieldRequirementCategory;
  required_on_payslip?: boolean;
  required_for_persistence?: boolean;
};

const PERSISTENCE_CRITICAL = new Set([
  'employee_name',
  'national_id',
  'employee_number',
  'pay_period',
]);

const REQUIRED: DefInput[] = [
  // Presentation: only these always render empty when missing (required_on_payslip).
  // More keys can be promoted later without changing Digital Form filter logic.
  { key: 'employee_name', section: 'identity', order: 10, category: 'required', required_on_payslip: true },
  { key: 'national_id', section: 'identity', order: 20, category: 'required', required_on_payslip: true },
];

const EXPECTED: DefInput[] = [
  { key: 'employer_name', section: 'employer', order: 25, category: 'expected' },
  { key: 'employer_id', section: 'employer', order: 26, category: 'expected' },
  { key: 'employer_address', section: 'employer', order: 27, category: 'expected' },
  { key: 'employment_start_date', section: 'identity', order: 28, category: 'expected' },
  { key: 'employment_scope', section: 'identity', order: 29, category: 'expected' },
  // Identity block order: name → national_id → employee_number → pay_period
  { key: 'employee_number', section: 'identity', order: 22, category: 'expected' },
  {
    key: 'pay_period',
    section: 'identity',
    order: 24,
    category: 'expected',
    required_on_payslip: true,
  },
  { key: 'base_salary', section: 'earnings', order: 40, category: 'expected' },
  { key: 'salary_calculation_basis', section: 'earnings', order: 45, category: 'expected' },
  { key: 'gross_salary', section: 'earnings', order: 50, category: 'expected' },
  { key: 'income_tax', section: 'deductions', order: 60, category: 'expected' },
  { key: 'national_insurance', section: 'deductions', order: 70, category: 'expected' },
  { key: 'total_deductions', section: 'deductions', order: 80, category: 'expected' },
  { key: 'net_salary', section: 'payment', order: 90, category: 'expected' },
  { key: 'amount_paid', section: 'payment', order: 95, category: 'expected' },
  { key: 'payment_method', section: 'payment', order: 100, category: 'expected' },
  { key: 'minimum_wage_monthly', section: 'other', order: 105, category: 'expected' },
  { key: 'minimum_wage_hourly', section: 'other', order: 106, category: 'expected' },
  { key: 'employee_id', section: 'identity', order: 115, category: 'expected' },
  { key: 'employment_type', section: 'identity', order: 120, category: 'expected' },
  { key: 'seniority_years', section: 'identity', order: 125, category: 'expected' },
  { key: 'department', section: 'identity', order: 130, category: 'expected' },
  { key: 'hourly_rate', section: 'earnings', order: 140, category: 'expected' },
  { key: 'regular_hours', section: 'earnings', order: 150, category: 'expected' },
  { key: 'overtime_hours', section: 'earnings', order: 160, category: 'expected' },
  { key: 'travel_expenses', section: 'earnings', order: 170, category: 'expected' },
  { key: 'health_tax', section: 'deductions', order: 180, category: 'expected' },
  { key: 'pension_employee', section: 'deductions', order: 190, category: 'expected' },
  { key: 'pension_employer', section: 'deductions', order: 200, category: 'expected' },
  { key: 'severance', section: 'deductions', order: 210, category: 'expected' },
  { key: 'training_fund', section: 'deductions', order: 220, category: 'expected' },
  { key: 'bank_name', section: 'payment', order: 230, category: 'expected' },
  { key: 'bank_branch', section: 'payment', order: 231, category: 'expected' },
  { key: 'bank_account', section: 'payment', order: 232, category: 'expected' },
  { key: 'vacation_balance', section: 'other', order: 240, category: 'expected' },
  { key: 'sick_leave_balance', section: 'other', order: 250, category: 'expected' },
  { key: 'messages', section: 'other', order: 260, category: 'expected' },
];

/** Keys known to the backend PAYSLIP_FIELD_KEYS tuple (must stay aligned). */
export const BACKEND_PAYSLIP_FIELD_KEYS = [
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

/** Mirror of backend PAYSLIP_CANONICAL_EXTRA_KEYS. */
export const BACKEND_PAYSLIP_CANONICAL_EXTRA_KEYS = [
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

function buildDefinition(input: DefInput): PayslipFieldDefinition {
  return {
    canonical_key: input.key,
    label_i18n_key: `payroll.fields.${input.key}`,
    section: input.section,
    display_order: input.order,
    requirement_category: input.category,
    editable: true,
    required_on_payslip: Boolean(input.required_on_payslip),
    required_for_persistence:
      input.required_for_persistence ?? PERSISTENCE_CRITICAL.has(input.key),
  };
}

function buildRegistry(): Record<string, PayslipFieldDefinition> {
  const defs: Record<string, PayslipFieldDefinition> = {};
  for (const item of [...REQUIRED, ...EXPECTED]) {
    defs[item.key] = buildDefinition(item);
  }
  let order = 900;
  for (const key of [...BACKEND_PAYSLIP_FIELD_KEYS, ...BACKEND_PAYSLIP_CANONICAL_EXTRA_KEYS]) {
    if (defs[key]) continue;
    defs[key] = buildDefinition({
      key,
      section: 'other',
      order,
      category: 'other',
    });
    order += 10;
  }
  return defs;
}

export const PAYSLIP_FIELD_REGISTRY = buildRegistry();

/**
 * Keys that may carry National ID for display/compat.
 * Prefer national_id. Legacy employee_id only counts when it looks like an Israeli ID.
 */
export const NATIONAL_ID_FIELD_KEYS = ['national_id'] as const;

export function getPayslipFieldDefinition(key: string): PayslipFieldDefinition | null {
  const normalized = key.trim();
  if (!normalized) return null;
  return PAYSLIP_FIELD_REGISTRY[normalized] ?? null;
}

export function requirementCategoryForKey(key: string): FieldRequirementCategory {
  return getPayslipFieldDefinition(key)?.requirement_category ?? 'other';
}

export function requiredOnPayslipKeys(): string[] {
  return Object.values(PAYSLIP_FIELD_REGISTRY)
    .filter((item) => item.required_on_payslip)
    .sort((a, b) => a.display_order - b.display_order)
    .map((item) => item.canonical_key);
}

export function displayOrderForKey(key: string): number {
  return getPayslipFieldDefinition(key)?.display_order ?? 10_000;
}

/** True when value looks like Israeli National ID digits (legacy employee_id compat). */
export function looksLikeNationalIdDigits(value: unknown): boolean {
  if (value == null) return false;
  const digits = String(value).replace(/\D/g, '');
  return digits.length === 9;
}

export function registrySnapshotForSync(): Record<
  string,
  {
    requirement_category: FieldRequirementCategory;
    section: PayslipFieldSection;
    display_order: number;
    required_on_payslip: boolean;
    required_for_persistence: boolean;
  }
> {
  const out: ReturnType<typeof registrySnapshotForSync> = {};
  for (const [key, item] of Object.entries(PAYSLIP_FIELD_REGISTRY).sort(([a], [b]) =>
    a.localeCompare(b),
  )) {
    out[key] = {
      requirement_category: item.requirement_category,
      section: item.section,
      display_order: item.display_order,
      required_on_payslip: item.required_on_payslip,
      required_for_persistence: item.required_for_persistence,
    };
  }
  return out;
}
