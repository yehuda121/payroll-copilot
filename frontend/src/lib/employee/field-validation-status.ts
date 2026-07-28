import type { ExtractedPayslipField, ValidationFinding } from '../../types/api';
import type { GuestValidationReport, RuleEvaluationOutcome } from '../../types/validation-report';
import type { FieldVisualStatus } from '../../features/guest/landing/fieldGuidance';
import type { ComparisonField, IdentityCheck, PeriodCheck } from '../../services/employeePortal';
import {
  findingIsMissingData,
  mapCompareToCardStatus,
  mapFindingToCardStatus,
} from './validation-display';
import {
  boundRuleIdsForField,
  fieldHasExplicitBindings,
} from './validation-taxonomy';
import { requiredOnPayslipKeys } from './payslip-field-registry';

export type FieldNeutralKind =
  | 'not_checked'
  | 'not_applicable'
  | 'insufficient_evidence'
  | 'missing_required';

export type EmployeeFieldValidationMeta = {
  status: FieldVisualStatus;
  labelKey: string;
  explanation: string | null;
  expected: string | null;
  actual: string | null;
  confidencePercent: number | null;
  /** Distinct neutral reason — never collapsed away internally. */
  neutralKind?: FieldNeutralKind;
  /** Payroll period proposed by the system — warning, not FAILED. */
  requiresApproval?: boolean;
  /** User confirmed a proposed value — keep PASSED styling even while draft is dirty. */
  userApproved?: boolean;
};

function statusRank(status: FieldVisualStatus): number {
  // FAILED > UNCERTAIN > PASSED > neutral(unchecked)
  if (status === 'failed') return 0;
  if (status === 'uncertain') return 1;
  if (status === 'passed') return 2;
  return 3;
}

function pickWorse(
  a: EmployeeFieldValidationMeta | null,
  b: EmployeeFieldValidationMeta,
): EmployeeFieldValidationMeta {
  if (!a) return b;
  return statusRank(b.status) < statusRank(a.status) ? b : a;
}

function isRequiredPresenceFinding(finding: ValidationFinding): boolean {
  const message = (finding.message_key || '').toLowerCase();
  const ruleId = (finding.rule_id || '').toLowerCase();
  return (
    message.includes('required_field_missing') ||
    ruleId.startsWith('sanity.required.')
  );
}

function metaFromFinding(finding: ValidationFinding): EmployeeFieldValidationMeta {
  const isMissingRequired = isRequiredPresenceFinding(finding);
  // Missing required_on_payslip / insufficient data → attention (uncertain), never FAILED.
  const status: FieldVisualStatus =
    isMissingRequired || findingIsMissingData(finding)
      ? 'uncertain'
      : mapFindingToCardStatus(finding);
  const neutralKind: FieldNeutralKind | undefined = isMissingRequired
    ? 'missing_required'
    : findingIsMissingData(finding)
      ? 'insufficient_evidence'
      : status === 'unchecked'
        ? 'not_checked'
        : undefined;
  return {
    status,
    labelKey: isMissingRequired
      ? 'employee.validation.status.missingRequired'
      : `employee.validation.status.${status}`,
    explanation:
      finding.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(finding.explanation)
        ? finding.explanation
        : null,
    expected: finding.expected_value,
    actual: finding.actual_value,
    confidencePercent:
      finding.confidence != null && !Number.isNaN(finding.confidence)
        ? Math.round(finding.confidence * 100)
        : null,
    neutralKind,
  };
}

function metaFromCompare(field: ComparisonField): EmployeeFieldValidationMeta {
  const status = mapCompareToCardStatus(field.status);
  return {
    status,
    labelKey: `employee.validation.status.${status}`,
    explanation: null,
    expected: field.expected_display,
    actual: field.extracted_display,
    confidencePercent: null,
    neutralKind: status === 'unchecked' ? 'not_checked' : undefined,
  };
}

function outcomesByRuleId(
  outcomes: RuleEvaluationOutcome[] | undefined,
): Map<string, RuleEvaluationOutcome> {
  const map = new Map<string, RuleEvaluationOutcome>();
  for (const item of outcomes ?? []) {
    const ruleId = (item.rule_id || '').trim();
    if (ruleId) map.set(ruleId, item);
  }
  return map;
}

/**
 * Map extraction fields + validation report to per-field visual status.
 *
 * Aggregation rules:
 * - Only bind findings via explicit FIELD_RULE_BINDINGS (no fuzzy guessing).
 * - Identity/period gates bind to their field keys when provided.
 * - Precedence: FAILED > UNCERTAIN > PASSED > neutral.
 * - Missing required_on_payslip → UNCERTAIN/missing_required (never FAILED).
 * - PASS only when rule_outcomes authoritatively say passed (no fabricated PASS).
 */
export function buildEmployeeFieldValidationMap(
  fields: ExtractedPayslipField[] | undefined,
  report: GuestValidationReport | null,
  options?: {
    identity?: IdentityCheck | null;
    period?: PeriodCheck | null;
  },
): Record<string, EmployeeFieldValidationMeta> {
  const out: Record<string, EmployeeFieldValidationMeta> = {};
  const findings = report?.findings ?? [];
  const fieldList = fields ?? [];
  const byKey = new Map(fieldList.map((field) => [field.key, field]));
  const outcomeMap = outcomesByRuleId(report?.ruleOutcomes);

  // Ensure required keys are considered even when missing from extraction list.
  for (const key of requiredOnPayslipKeys()) {
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        value: null,
        confidence: null,
        source_text: null,
        status: 'MISSING',
        edited_by_user: false,
      });
    }
  }

  for (const [key, field] of byKey) {
    let best: EmployeeFieldValidationMeta | null = null;

    if (options?.identity) {
      // National ID gate binds only to national_id presentation key.
      // employee_id is payroll/system ID and must not inherit the NID gate color.
      const identityKey = key === 'national_id' ? 'national_id' : key;
      const identityField = options.identity.fields.find((item) => item.key === identityKey);
      if (identityField) {
        best = pickWorse(best, metaFromCompare(identityField));
      }
    }
    if (options?.period && key === 'pay_period') {
      best = pickWorse(best, {
        status: mapCompareToCardStatus(options.period.status),
        labelKey: `employee.validation.status.${mapCompareToCardStatus(options.period.status)}`,
        explanation: null,
        expected: `${options.period.selected_month}/${options.period.selected_year}`,
        actual:
          options.period.extracted_month && options.period.extracted_year
            ? `${options.period.extracted_month}/${options.period.extracted_year}`
            : null,
        confidencePercent: null,
        neutralKind:
          mapCompareToCardStatus(options.period.status) === 'unchecked'
            ? 'not_checked'
            : undefined,
      });
    }

    if (fieldHasExplicitBindings(key)) {
      const bound = new Set(boundRuleIdsForField(key));
      const matched = findings.filter((finding) => bound.has(finding.rule_id || ''));
      for (const finding of matched) {
        best = pickWorse(best, metaFromFinding(finding));
      }
      // Authoritative PASS only when every bound rule that ran passed,
      // and at least one bound rule was evaluated as passed.
      if (report && bound.size > 0 && matched.length === 0 && !best && outcomeMap.size > 0) {
        const boundOutcomes = [...bound]
          .map((ruleId) => outcomeMap.get(ruleId))
          .filter((item): item is RuleEvaluationOutcome => Boolean(item));
        const anyPassed = boundOutcomes.some((item) => item.outcome === 'passed');
        const anyFailed = boundOutcomes.some((item) => item.outcome === 'failed');
        const anyUncertain = boundOutcomes.some((item) => item.outcome === 'uncertain');
        if (anyPassed && !anyFailed && !anyUncertain) {
          best = {
            status: 'passed',
            labelKey: 'employee.validation.status.passed',
            explanation: null,
            expected: null,
            actual: null,
            confidencePercent: null,
          };
        }
      }
    }

    if (best) {
      out[key] = best;
      continue;
    }

    const statusUpper = (field.status || '').toUpperCase();
    const empty =
      statusUpper === 'MISSING' ||
      field.value == null ||
      String(field.value).trim() === '';

    if (empty && requiredOnPayslipKeys().includes(key)) {
      out[key] = {
        status: 'uncertain',
        labelKey: 'employee.validation.status.missingRequired',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent: null,
        neutralKind: 'missing_required',
      };
      continue;
    }

    if (report) {
      if (statusUpper === 'UNCERTAIN') {
        out[key] = {
          status: 'uncertain',
          labelKey: 'employee.validation.status.uncertain',
          explanation: null,
          expected: null,
          actual: null,
          confidencePercent:
            field.confidence != null && !Number.isNaN(field.confidence)
              ? Math.round(field.confidence * 100)
              : null,
        };
        continue;
      }
      out[key] = {
        status: 'unchecked',
        labelKey: 'employee.validation.status.unchecked',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent:
          empty || field.confidence == null || Number.isNaN(field.confidence)
            ? null
            : Math.round(field.confidence * 100),
        neutralKind: 'not_checked',
      };
      continue;
    }

    if (statusUpper === 'UNCERTAIN') {
      out[key] = {
        status: 'uncertain',
        labelKey: 'employee.validation.status.uncertain',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent:
          field.confidence != null && !Number.isNaN(field.confidence)
            ? Math.round(field.confidence * 100)
            : null,
      };
    } else if (statusUpper === 'MISSING' || empty) {
      out[key] = {
        status: 'uncertain',
        labelKey: 'employee.validation.status.missingRequired',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent: null,
        neutralKind: 'missing_required',
      };
    }
  }

  return out;
}

export function countValidationStatuses(
  map: Record<string, EmployeeFieldValidationMeta>,
): { passed: number; failed: number; uncertain: number; unchecked: number } {
  const counts = { passed: 0, failed: 0, uncertain: 0, unchecked: 0 };
  for (const meta of Object.values(map)) {
    counts[meta.status] += 1;
  }
  return counts;
}
