/**
 * Static business tips (not AI-generated) and short field explanation helpers.
 * AI explanations are derived only from deterministic validation findings.
 */

export type FieldGuidance = {
  tipKey?: string;
  explanationFromFinding?: string;
};

/** Optional static tips keyed by extraction / report field id. */
export const STATIC_FIELD_TIPS: Record<string, string> = {
  tax_credit_points: 'landingChat.tips.taxCredits',
  tax_credits: 'landingChat.tips.taxCredits',
  released_soldier: 'landingChat.tips.releasedSoldier',
  travel: 'landingChat.tips.travel',
  travel_expenses: 'landingChat.tips.travel',
  transportation: 'landingChat.tips.travel',
};

/** Maps common extraction keys to short explanation i18n keys when a finding exists. */
export const FIELD_EXPLAIN_KEYS: Record<string, string> = {
  employee_name: 'landingChat.explain.identity',
  employee_id: 'landingChat.explain.identity',
  national_id: 'landingChat.explain.identity',
  base_salary: 'landingChat.explain.salary',
  gross_salary: 'landingChat.explain.salary',
  net_salary: 'landingChat.explain.salary',
  tax_credit_points: 'landingChat.explain.taxCredits',
  tax_credits: 'landingChat.explain.taxCredits',
  pay_period: 'landingChat.explain.period',
};

export type FieldVisualStatus = 'passed' | 'failed' | 'uncertain' | 'unchecked';

export function mapFindingSeverityToFieldStatus(
  severity: string | null | undefined,
): FieldVisualStatus {
  const s = (severity || '').toLowerCase();
  if (s === 'critical' || s === 'failed' || s === 'error') return 'failed';
  if (s === 'warning' || s === 'uncertain') return 'uncertain';
  if (s === 'info' || s === 'pass' || s === 'passed') return 'passed';
  return 'unchecked';
}
