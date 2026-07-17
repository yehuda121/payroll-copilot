import type { ExtractedPayslipField, ValidationFinding } from '../../types/api';
import type { GuestValidationReport } from '../../types/validation-report';
import type { FieldVisualStatus } from '../../features/guest/landing/fieldGuidance';
import {
  findingIsMissingData,
  mapFindingToCardStatus,
} from './validation-display';

export type EmployeeFieldValidationMeta = {
  status: FieldVisualStatus;
  labelKey: string;
  explanation: string | null;
  expected: string | null;
  actual: string | null;
  confidencePercent: number | null;
};

function findingTouchesKey(finding: ValidationFinding, key: string): boolean {
  const needle = key.toLowerCase();
  const haystacks = [
    finding.rule_id,
    finding.message_key,
    finding.code,
    finding.message,
    finding.explanation,
  ]
    .filter(Boolean)
    .map((part) => String(part).toLowerCase());
  return haystacks.some((text) => text.includes(needle) || text.includes(needle.replace(/_/g, '.')));
}

/**
 * Map extraction fields + validation report to per-field visual status.
 * Prefer explicit findings; fall back to extraction confidence/status.
 * Missing-data findings are never shown as passed.
 */
export function buildEmployeeFieldValidationMap(
  fields: ExtractedPayslipField[] | undefined,
  report: GuestValidationReport | null,
): Record<string, EmployeeFieldValidationMeta> {
  const out: Record<string, EmployeeFieldValidationMeta> = {};
  if (!fields) return out;

  const findings = report?.findings ?? [];

  for (const field of fields) {
    const matched = findings.find((finding) => findingTouchesKey(finding, field.key));
    if (matched) {
      const status = findingIsMissingData(matched)
        ? 'unchecked'
        : mapFindingToCardStatus(matched);
      out[field.key] = {
        status,
        labelKey: `employee.validation.status.${status}`,
        explanation:
          matched.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(matched.explanation)
            ? matched.explanation
            : null,
        expected: matched.expected_value,
        actual: matched.actual_value,
        confidencePercent:
          matched.confidence != null && !Number.isNaN(matched.confidence)
            ? Math.round(matched.confidence * 100)
            : null,
      };
      continue;
    }

    const statusUpper = (field.status || '').toUpperCase();
    if (report) {
      if (statusUpper === 'UNCERTAIN') {
        const pct =
          field.confidence != null && !Number.isNaN(field.confidence)
            ? Math.round(field.confidence * 100)
            : null;
        out[field.key] = {
          status: 'uncertain',
          labelKey: 'employee.validation.status.uncertain',
          explanation: null,
          expected: null,
          actual: null,
          confidencePercent: pct,
        };
        continue;
      }
      if (statusUpper === 'MISSING' || field.value == null || String(field.value).trim() === '') {
        out[field.key] = {
          status: 'unchecked',
          labelKey: 'employee.validation.status.unchecked',
          explanation: null,
          expected: null,
          actual: null,
          confidencePercent: null,
        };
        continue;
      }
      out[field.key] = {
        status: 'passed',
        labelKey: 'employee.validation.status.passed',
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

    if (statusUpper === 'UNCERTAIN') {
      const pct =
        field.confidence != null && !Number.isNaN(field.confidence)
          ? Math.round(field.confidence * 100)
          : null;
      out[field.key] = {
        status: 'uncertain',
        labelKey: 'employee.validation.status.uncertain',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent: pct,
      };
    } else if (statusUpper === 'MISSING') {
      out[field.key] = {
        status: 'unchecked',
        labelKey: 'employee.validation.status.unchecked',
        explanation: null,
        expected: null,
        actual: null,
        confidencePercent: null,
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
