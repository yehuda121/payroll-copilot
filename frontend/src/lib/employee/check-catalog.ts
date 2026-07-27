/**
 * Stable check-row catalog for Employee/Contract and Law tabs.
 * PASS is shown only when ValidationReport.ruleOutcomes authoritatively says passed.
 * Catalog IDs must stay aligned with backend validation_catalog (all 17 labor-law rules).
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

/**
 * Stable display order — identity/contract first, then labor-law by domain,
 * then department/historical. Mirrors backend validation_catalog display_order.
 */
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
  'legal.overtime.weekly_limit',
  'legal.overtime.rate_tier_1',
  'legal.overtime.rate_tier_2',
  'legal.vacation.annual_entitlement',
  'legal.vacation.monthly_accrual',
  'legal.sick_leave.annual_entitlement',
  'legal.pension.contribution',
  'legal.pension.employer_contribution',
  'legal.pension.severance',
  'legal.tax.income_brackets',
  'legal.tax.credit_point',
  'legal.transportation.max_allowance',
  'legal.transportation.public_transport',
  'legal.youth.minimum_age',
  'legal.youth.max_daily_hours',
  'department.intern.weekly_hours_limit',
  'department.lawyers.overtime_cap',
  'historical.salary_drift',
] as const;

export const LABOR_LAW_RULE_IDS: readonly string[] = CHECK_CATALOG_RULE_IDS.filter((id) =>
  id.startsWith('legal.'),
);

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
  /** Immutable deterministic outcome when review overlay is present. */
  deterministicStatus: CheckRowStatus | null;
  explanation: string | null;
  skipReasonKey: string | null;
  reasonCode: string | null;
  findingId?: string | null;
  approvalReason?: string | null;
};

function catalogUiGroup(ruleId: string): 'employee_checks' | 'law_checks' {
  const taxonomy = taxonomyForRuleId(ruleId, null);
  if (taxonomy) {
    const group = uiGroupForTaxonomy(taxonomy);
    if (group === 'law_checks') return 'law_checks';
  }
  if (ruleId.startsWith('legal.') || ruleId.startsWith('department.') || ruleId.startsWith('historical.')) {
    return 'law_checks';
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

function normalizeOutcome(outcome: string | null | undefined): string {
  if (!outcome) return 'not_run';
  if (outcome === 'skipped') return 'not_run';
  return outcome;
}

function knownSkipReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  const known = new Set([
    'employee_not_identified',
    'no_confirmed_contract',
    'MISSING_PAYSLIP_DATA',
    'RULE_NOT_READY',
    'NO_APPLICABLE_LEGAL_VERSION',
    'NOT_APPLICABLE',
    'UNSUPPORTED_SCOPE',
    'RULE_DISABLED',
    'DEPENDENCY_UNAVAILABLE',
    'EXECUTION_ERROR',
    'EMPLOYEE_NOT_IDENTIFIED',
    'NO_CONFIRMED_CONTRACT',
  ]);
  if (known.has(reason)) return reason;
  return null;
}

function notRunExplanation(
  outcome: RuleEvaluationOutcome | undefined,
  t: TFunction,
): { explanation: string | null; skipReasonKey: string | null; reasonCode: string | null } {
  const reasonCode = outcome?.reason_code ?? null;
  const skipReason = knownSkipReason(outcome?.skip_reason) ?? knownSkipReason(reasonCode);
  if (outcome?.message && outcome.message.trim()) {
    return { explanation: outcome.message, skipReasonKey: skipReason, reasonCode };
  }
  if (skipReason) {
    return {
      explanation: t(`employee.validation.notRunReasons.${skipReason}`, {
        defaultValue: t('employee.validation.status.notRun'),
      }),
      skipReasonKey: skipReason,
      reasonCode,
    };
  }
  return {
    explanation: t('employee.validation.status.notRun'),
    skipReasonKey: null,
    reasonCode,
  };
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
  const approvalsByRule = new Map<string, NonNullable<GuestValidationReport['manualApprovals']>[number]>();
  for (const item of report?.manualApprovals ?? []) {
    const rid = (item.rule_id || '').trim();
    if (rid) approvalsByRule.set(rid, item);
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
    let reasonCode: string | null = null;

    const normalized = normalizeOutcome(outcome?.outcome);

    if (hasAuthoritativeOutcomes && (normalized === 'not_run' || !outcome)) {
      // Explicit NOT_RUN (or missing outcome for a catalog rule when outcomes exist)
      if (outcome && normalized === 'not_run') {
        status = 'not_run';
        const nr = notRunExplanation(outcome, t);
        explanation = nr.explanation;
        skipReasonKey = nr.skipReasonKey;
        reasonCode = nr.reasonCode;
      } else if (!outcome) {
        status = 'not_run';
        explanation = t('employee.validation.status.notRun');
      }
    } else if (hasAuthoritativeOutcomes && normalized === 'uncertain') {
      status = 'uncertain';
      explanation =
        outcome?.message ||
        (finding
          ? (finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
              ? finding.explanation
              : null) || translateFindingMessage(finding.message_key, t)
          : t('employee.validation.status.uncertain'));
      reasonCode = outcome?.reason_code ?? null;
    } else if (hasAuthoritativeOutcomes && normalized === 'passed' && !finding) {
      status = 'passed';
      explanation = null;
    } else if (finding) {
      status = statusFromFinding(finding);
      explanation =
        (finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
          ? finding.explanation
          : null) || translateFindingMessage(finding.message_key, t);
      // Authoritative outcome wins over finding for passed/failed/uncertain when present
      if (hasAuthoritativeOutcomes && normalized === 'passed' && status !== 'manually_approved') {
        // Finding present with passed outcome is unusual; keep finding status if failed
        if (status === 'failed' || status === 'uncertain') {
          // Prefer finding severity when present
        } else {
          status = 'passed';
          explanation = null;
        }
      } else if (hasAuthoritativeOutcomes && normalized === 'failed') {
        if (status !== 'manually_approved') status = 'failed';
      }
    } else if (hasAuthoritativeOutcomes && normalized === 'failed') {
      status = 'failed';
      explanation = outcome?.message ?? null;
    } else {
      status = 'not_run';
      explanation = t('employee.validation.status.notRun');
    }

    const deterministicStatus = status === 'manually_approved' ? null : status;
    const approval = approvalsByRule.get(ruleId);
    let approvalReason: string | null = null;
    if (approval && status !== 'manually_approved') {
      // Overlay review without rewriting deterministic status semantics in data.
      approvalReason = approval.reason ?? null;
      status = 'manually_approved';
    } else if (status === 'manually_approved' && finding?.manual_approval) {
      approvalReason =
        typeof finding.manual_approval.reason === 'string'
          ? finding.manual_approval.reason
          : null;
    }

    rows.push({
      key: `check-${ruleId}`,
      ruleId,
      taxonomy,
      uiGroup,
      title,
      status,
      deterministicStatus:
        status === 'manually_approved'
          ? deterministicStatus ??
            (normalizeOutcome(
              (approval?.original_deterministic_status ||
                approval?.deterministic_status ||
                outcome?.outcome) as string,
            ) as CheckRowStatus)
          : null,
      explanation,
      skipReasonKey,
      reasonCode,
      findingId: finding?.id ?? null,
      approvalReason,
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
    const status = statusFromFinding(finding);
    rows.push({
      key: `finding-extra-${finding.id}`,
      ruleId,
      taxonomy,
      uiGroup,
      title: translateFindingTitle(finding.message_key, t, ruleId),
      status,
      deterministicStatus: status === 'manually_approved' ? 'failed' : null,
      explanation:
        (finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
          ? finding.explanation
          : null) || translateFindingMessage(finding.message_key, t),
      skipReasonKey: null,
      reasonCode: null,
      findingId: finding.id,
      approvalReason:
        finding.manual_approval && typeof finding.manual_approval.reason === 'string'
          ? finding.manual_approval.reason
          : null,
    });
  }

  return rows;
}

export function summarizeCheckRows(rows: CheckCatalogRow[]): {
  total: number;
  executed: number;
  passed: number;
  failed: number;
  uncertain: number;
  not_run: number;
  manually_approved: number;
} {
  const summary = {
    total: rows.length,
    executed: 0,
    passed: 0,
    failed: 0,
    uncertain: 0,
    not_run: 0,
    manually_approved: 0,
  };
  for (const row of rows) {
    if (row.status === 'manually_approved') summary.manually_approved += 1;
    const effective =
      row.status === 'manually_approved' ? row.deterministicStatus || 'not_run' : row.status;
    if (effective === 'passed') {
      summary.passed += 1;
      summary.executed += 1;
    } else if (effective === 'failed') {
      summary.failed += 1;
      summary.executed += 1;
    } else if (effective === 'uncertain') {
      summary.uncertain += 1;
      summary.executed += 1;
    } else {
      summary.not_run += 1;
    }
  }
  return summary;
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
        css: 'is-manually-approved',
      };
    default:
      return {
        icon: '–',
        label: t('employee.validation.status.notRun'),
        css: 'is-not-run',
      };
  }
}
