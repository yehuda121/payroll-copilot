/**
 * Employee Portal validation display helpers.
 * Static UI labels come from i18n; extracted/user values stay untouched.
 */

import type { TFunction } from 'i18next';
import type { ValidationFinding } from '../../types/api';

export type EmployeeCardStatus = 'passed' | 'failed' | 'uncertain' | 'unchecked';

const FINDING_KEY_ALIASES: Record<string, string> = {
  'validation.missing_data': 'validation_missing_data',
  'validation.overtime.daily_limit_exceeded': 'validation_overtime_daily_limit_exceeded',
  'validation.minimum_wage.below_threshold': 'validation_minimum_wage_below_threshold',
  'validation.pension.insufficient_contribution': 'validation_pension_insufficient_contribution',
  'validation.youth.below_minimum_age': 'validation_youth_below_minimum_age',
  'validation.department.intern_hours_exceeded': 'validation_department_intern_hours_exceeded',
  'validation.department.lawyers_overtime_cap': 'validation_department_lawyers_overtime_cap',
  'validation.historical.salary_drift': 'validation_historical_salary_drift',
};

const FINDING_TITLE_KEYS: Record<string, string> = {
  validation_missing_data: 'employee.validation.checkTitles.missingData',
  validation_overtime_daily_limit_exceeded: 'employee.validation.checkTitles.overtime',
  validation_minimum_wage_below_threshold: 'employee.validation.checkTitles.minimumWage',
  validation_pension_insufficient_contribution: 'employee.validation.checkTitles.pension',
  validation_youth_below_minimum_age: 'employee.validation.checkTitles.youth',
  validation_department_intern_hours_exceeded: 'employee.validation.checkTitles.internHours',
  validation_department_lawyers_overtime_cap: 'employee.validation.checkTitles.lawyerOvertime',
  validation_historical_salary_drift: 'employee.validation.checkTitles.salaryDrift',
};

const SCOPE_TITLE_KEYS: Record<string, string> = {
  payroll_rules: 'employee.validation.scope.payroll_rules',
  attendance: 'employee.validation.scope.attendance',
  employment_agreement: 'employee.validation.scope.employment_agreement',
  tax_benefits: 'employee.validation.scope.tax_benefits',
  historical_comparison: 'employee.validation.scope.historical_comparison',
};

function findingAlias(messageKey: string | null | undefined): string {
  const raw = (messageKey || '').trim();
  if (!raw) return '';
  return FINDING_KEY_ALIASES[raw] || raw.replaceAll('.', '_');
}

/** Map identity/period comparison status to card visual status. */
export function mapCompareToCardStatus(status: string): EmployeeCardStatus {
  if (status === 'match') return 'passed';
  if (status === 'mismatch') return 'failed';
  if (status === 'uncertain') return 'uncertain';
  // missing / cannot_validate / extracted → cannot validate
  return 'unchecked';
}

/** Map validation scope item status. */
export function mapScopeToCardStatus(
  status: string,
  reason?: string | null,
): EmployeeCardStatus {
  const reasonText = (reason || '').toLowerCase();
  const looksMissing =
    reasonText.includes('missing') ||
    reasonText.includes('incomplete') ||
    reasonText.includes('not_available') ||
    reasonText.includes('unable');
  if (status === 'not_available' || looksMissing) return 'unchecked';
  if (status === 'completed') return 'passed';
  if (status === 'partial') return 'uncertain';
  return 'unchecked';
}

/**
 * Map a deterministic finding to card status.
 * Missing-data / info findings are never "passed".
 */
export function mapFindingToCardStatus(finding: {
  severity?: string | null;
  message_key?: string | null;
  code?: string | null;
  confidence?: number | null;
}): EmployeeCardStatus {
  const key = (finding.message_key || finding.code || '').toLowerCase();
  const severity = (finding.severity || '').toLowerCase();

  if (
    key.includes('missing_data') ||
    key.includes('missing') ||
    severity === 'info' ||
    severity === 'unable' ||
    severity === 'not_available'
  ) {
    return 'unchecked';
  }

  if (severity === 'critical' || severity === 'failed' || severity === 'error') {
    return 'failed';
  }
  if (severity === 'warning' || severity === 'uncertain') {
    return 'uncertain';
  }
  if (severity === 'pass' || severity === 'passed') {
    return 'passed';
  }

  // Low confidence after execution → AI uncertain
  if (
    finding.confidence != null &&
    !Number.isNaN(finding.confidence) &&
    finding.confidence > 0 &&
    finding.confidence < 0.7
  ) {
    return 'uncertain';
  }

  return 'unchecked';
}

export function translateFindingMessage(
  messageKey: string | null | undefined,
  t: TFunction,
): string {
  const alias = findingAlias(messageKey);
  if (!alias) return t('employee.validation.findings.generic');
  const path = `employee.validation.findings.${alias}`;
  const text = t(path);
  if (text === path || text.startsWith('employee.validation.findings.')) {
    return t('employee.validation.findings.generic');
  }
  return text;
}

export function translateFindingTitle(
  messageKey: string | null | undefined,
  t: TFunction,
): string {
  const alias = findingAlias(messageKey);
  const titlePath = FINDING_TITLE_KEYS[alias];
  if (titlePath) return t(titlePath);
  return translateFindingMessage(messageKey, t);
}

export function translateScopeTitle(scopeKey: string, label: string | null | undefined, t: TFunction): string {
  const path = SCOPE_TITLE_KEYS[scopeKey];
  if (path) return t(path);
  // Never show snake_case / dotted backend identifiers as titles.
  if (label && !/^[a-z][a-z0-9_.-]*$/i.test(label)) return label;
  return t('employee.validation.checkTitles.genericCheck');
}

export function translateScopeReason(reason: string | null | undefined, t: TFunction): string | null {
  if (!reason) return null;
  const alias = reason.replaceAll('.', '_');
  const path = `employee.validation.scopeReasons.${alias}`;
  const text = t(path);
  if (text !== path && !text.startsWith('employee.validation.scopeReasons.')) return text;
  // Reason may already be human text from backend localization — keep as-is (not user PII).
  if (/^[a-z][a-z0-9_.-]*$/i.test(reason)) {
    return t('employee.validation.scopeReasons.generic');
  }
  return reason;
}

export function translateOverallResult(
  result: string | null | undefined,
  t: TFunction,
): string {
  switch ((result || '').toLowerCase()) {
    case 'pass':
    case 'passed':
      return t('report.overallPassed');
    case 'warnings':
    case 'warning':
      return t('report.overallWarnings');
    case 'critical':
    case 'failed':
    case 'error':
      return t('report.overallCritical');
    default:
      return t('report.overallPending');
  }
}

export function findingIsMissingData(finding: Pick<ValidationFinding, 'message_key' | 'severity' | 'code'>): boolean {
  const key = `${finding.message_key || ''} ${finding.code || ''}`.toLowerCase();
  const severity = (finding.severity || '').toLowerCase();
  return key.includes('missing_data') || key.includes('missing') || severity === 'info';
}
