/**
 * Validation taxonomy — FE mirror of backend validation_taxonomy.py.
 * Derive-on-read; does not change PASS/FAIL.
 */

export type ValidationTaxonomy = 'sanity' | 'employee' | 'contract' | 'law';

export type ValidationUiGroup = 'employee_checks' | 'law_checks' | 'digital';

const RULE_ID_TAXONOMY: Record<string, ValidationTaxonomy> = {
  'legal.overtime.daily_limit': 'law',
  'legal.minimum_wage': 'law',
  'legal.pension.contribution': 'law',
  'legal.youth.minimum_age': 'law',
  'department.intern.weekly_hours_limit': 'contract',
  'department.lawyers.overtime_cap': 'contract',
  'historical.salary_drift': 'employee',
};

const CATEGORY_FALLBACK: Record<string, ValidationTaxonomy> = {
  legal: 'law',
  tax: 'law',
  pension: 'law',
  overtime: 'law',
  vacation: 'law',
  transportation: 'law',
  holiday: 'law',
  department: 'contract',
  contract: 'contract',
  historical: 'employee',
  company: 'employee',
};

/** Clear field ↔ rule_id bindings only (no guessing). */
export const FIELD_RULE_BINDINGS: Record<string, readonly string[]> = {
  overtime_hours: ['legal.overtime.daily_limit'],
  hourly_rate: ['legal.minimum_wage'],
  gross_salary: ['legal.pension.contribution', 'historical.salary_drift'],
  pension_employee: ['legal.pension.contribution'],
  regular_hours: ['department.intern.weekly_hours_limit'],
  employee_id: [],
  national_id: [],
  employee_name: [],
  pay_period: [],
};

export function taxonomyForRuleId(
  ruleId: string | null | undefined,
  category?: string | null,
): ValidationTaxonomy | null {
  const rid = (ruleId || '').trim();
  if (rid && RULE_ID_TAXONOMY[rid]) return RULE_ID_TAXONOMY[rid];
  if (category) {
    const mapped = CATEGORY_FALLBACK[String(category).trim().toLowerCase()];
    if (mapped) return mapped;
  }
  const lower = rid.toLowerCase();
  if (
    lower.startsWith('legal.') ||
    lower.startsWith('validation.overtime') ||
    lower.includes('minimum_wage')
  ) {
    return 'law';
  }
  if (lower.startsWith('department.')) return 'contract';
  if (lower.startsWith('historical.')) return 'employee';
  return null;
}

export function uiGroupForTaxonomy(taxonomy: ValidationTaxonomy): ValidationUiGroup {
  if (taxonomy === 'employee' || taxonomy === 'contract') return 'employee_checks';
  if (taxonomy === 'law') return 'law_checks';
  return 'digital';
}

export function boundRuleIdsForField(fieldKey: string): readonly string[] {
  return FIELD_RULE_BINDINGS[fieldKey.trim()] ?? [];
}

export function fieldHasExplicitBindings(fieldKey: string): boolean {
  return Object.prototype.hasOwnProperty.call(FIELD_RULE_BINDINGS, fieldKey.trim());
}
