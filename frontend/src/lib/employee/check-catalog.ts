/**
 * Stable check-row catalog for Employee/Contract and Law tabs.
 * PASS is shown only when ValidationReport.ruleOutcomes authoritatively says passed.
 */

import type { TFunction } from 'i18next';
import type { GuestValidationReport, RuleEvaluationOutcome } from '../../types/validation-report';
import type { ValidationFinding } from '../../types/api';
import {
  findingIsMissingData,
  mapFindingToCardStatus,
  translateFindingMessage,
  translateFindingTitle,
  type EmployeeCardStatus,
} from './validation-display';
import {
  taxonomyForRuleId,
  uiGroupForTaxonomy,
  type ValidationTaxonomy,
} from './validation-taxonomy';

/** Catalog of user-facing EMPLOYEE / CONTRACT / LAW checks (not SANITY). */
export const CHECK_CATALOG_RULE_IDS: readonly string[] = [
  'employee.national_id.match',
  'employee.name.match',
  'employee.employee_number.match',
  'employee.employment_type.match',
  'employee.pay_period.match',
  'contract.employment_commencement_date.match',
  'contract.salary_basis.match',
  'contract.hourly_rate.match',
  'legal.minimum_wage',
  'legal.overtime.daily_limit',
  'legal.pension.contribution',
  'legal.youth.minimum_age',
  'department.intern.weekly_hours_limit',
  'department.lawyers.overtime_cap',
  'historical.salary_drift',
] as const;

export type CheckRowStatus =
  | 'passed'
  | 'failed'
  | 'uncertain'
  | 'not_run'
  | 'manually_approved';

export type CheckCatalogRow = {
  key: string;
  ruleId: string;
  taxonomy: ValidationTaxonomy | null;
  uiGroup: 'employee_checks' | 'law_checks';
  title: string;
  status: CheckRowStatus;
  explanation: string | null;
  skipReasonKey: string | null;
  findingId?: string | null;
};

function catalogUiGroup(ruleId: string): 'employee_checks' | 'law_checks' {
  const taxonomy = taxonomyForRuleId(ruleId, null);
  if (taxonomy) {
    const group = uiGroupForTaxonomy(taxonomy);
    if (group === 'law_checks') return 'law_checks';
  }
  return 'employee_checks';
}

function findingForRule(
  findings: ValidationFinding[],
  ruleId: string,
): ValidationFinding | undefined {
  return findings.find((finding) => (finding.rule_id || finding.code) === ruleId);
}

function statusFromFinding(finding: ValidationFinding): CheckRowStatus {
  if (finding.display_status === 'manually_approved' || finding.manual_approval) {
    return 'manually_approved';
  }
  if (findingIsMissingData(finding)) return 'uncertain';
  const mapped: EmployeeCardStatus = mapFindingToCardStatus(finding);
  if (mapped === 'failed') return 'failed';
  if (mapped === 'uncertain') return 'uncertain';
  if (mapped === 'passed') return 'passed';
  return 'uncertain';
}

function knownSkipReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  if (reason === 'employee_not_identified' || reason === 'no_confirmed_contract') {
    return reason;
  }
  return null;
}

/**
 * Build stable check rows for a UI group.
 * Never fabricates PASS without rule_outcomes.passed.
 */
export function buildCheckCatalogRows(
  report: GuestValidationReport | null,
  t: TFunction,
  checkGroup: 'employee_checks' | 'law_checks' | 'all' = 'all',
): CheckCatalogRow[] {
  const findings = report?.findings ?? [];
  const outcomes = new Map<string, RuleEvaluationOutcome>();
  for (const item of report?.ruleOutcomes ?? []) {
    if (item.rule_id) outcomes.set(item.rule_id, item);
  }
  const hasAuthoritativeOutcomes = outcomes.size > 0;

  const rows: CheckCatalogRow[] = [];
  for (const ruleId of CHECK_CATALOG_RULE_IDS) {
    const uiGroup = catalogUiGroup(ruleId);
    if (checkGroup !== 'all' && uiGroup !== checkGroup) continue;

    const finding = findingForRule(findings, ruleId);
    const outcome = outcomes.get(ruleId);
    const taxonomy = taxonomyForRuleId(ruleId, null);
    const title = translateFindingTitle(
      finding?.message_key || ruleId,
      t,
      ruleId,
    );

    let status: CheckRowStatus = 'not_run';
    let explanation: string | null = null;
    let skipReasonKey: string | null = null;

    if (finding) {
      status = statusFromFinding(finding);
      explanation =
        (finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
          ? finding.explanation
          : null) || translateFindingMessage(finding.message_key, t);
    } else if (hasAuthoritativeOutcomes && outcome?.outcome === 'passed') {
      status = 'passed';
      explanation = null;
    } else if (hasAuthoritativeOutcomes && outcome?.outcome === 'failed') {
      // Finding missing but outcome says failed — treat as uncertain attention.
      status = 'uncertain';
    } else if (hasAuthoritativeOutcomes && outcome?.outcome === 'skipped') {
      status = 'not_run';
      skipReasonKey = knownSkipReason(outcome.skip_reason);
    } else {
      status = 'not_run';
    }

    rows.push({
      key: `check-${ruleId}`,
      ruleId,
      taxonomy,
      uiGroup,
      title,
      status,
      explanation,
      skipReasonKey,
      findingId: finding?.id ?? null,
    });
  }

  // Surface unexpected non-SANITY findings that are not in the static catalog.
  for (const finding of findings) {
    const ruleId = (finding.rule_id || finding.code || '').trim();
    if (!ruleId || CHECK_CATALOG_RULE_IDS.includes(ruleId)) continue;
    const taxonomy = taxonomyForRuleId(ruleId, null);
    if (taxonomy === 'sanity') continue;
    const group = taxonomy ? uiGroupForTaxonomy(taxonomy) : 'employee_checks';
    if (group === 'digital') continue;
    const uiGroup = group === 'law_checks' ? 'law_checks' : 'employee_checks';
    if (checkGroup !== 'all' && uiGroup !== checkGroup) continue;
    rows.push({
      key: `finding-extra-${finding.id}`,
      ruleId,
      taxonomy,
      uiGroup,
      title: translateFindingTitle(finding.message_key, t, ruleId),
      status: statusFromFinding(finding),
      explanation:
        (finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
          ? finding.explanation
          : null) || translateFindingMessage(finding.message_key, t),
      skipReasonKey: null,
      findingId: finding.id,
    });
  }

  return rows;
}

export function checkRowStatusVisual(
  status: CheckRowStatus,
  t: TFunction,
): { icon: string; label: string; css: string } {
  switch (status) {
    case 'passed':
      return { icon: '✓', label: t('employee.validation.status.passed'), css: 'is-passed' };
    case 'failed':
      return { icon: '✕', label: t('employee.validation.status.failed'), css: 'is-failed' };
    case 'uncertain':
      return { icon: '⚠', label: t('employee.validation.status.uncertain'), css: 'is-uncertain' };
    case 'manually_approved':
      return {
        icon: '✓',
        label: t('employee.validation.status.manuallyApproved', {
          defaultValue: t('employee.validation.status.passed'),
        }),
        css: 'is-passed',
      };
    default:
      return {
        icon: '–',
        label: t('employee.validation.status.notRun'),
        css: 'is-not-run',
      };
  }
}
