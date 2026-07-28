/**
 * Presentation overlay for payroll period found / missing proposal.
 * Does not change extraction — only Digital Payslip display + local approval.
 */

import type { ExtractedPayslipField } from '../../types/api';
import type { FieldDraft } from '../../hooks/useEmployeePayslipFlow';
import type { EmployeeFieldValidationMeta } from './field-validation-status';
import type { PeriodCheck } from '../../services/employeePortal';
import {
  isPayPeriodMissing,
  proposedPayrollPeriodValue,
} from './payroll-period-proposal';

export type PayrollPeriodPresentation = {
  displayDrafts: Record<string, FieldDraft>;
  validationMap: Record<string, EmployeeFieldValidationMeta>;
  /** True when the system proposed a period that still needs accountant confirmation. */
  requiresApproval: boolean;
  proposedValue: string;
};

function fieldPayPeriodValue(fields: ExtractedPayslipField[] | undefined): string {
  const field = fields?.find((item) => item.key === 'pay_period');
  if (field?.value == null) return '';
  return String(field.value).trim();
}

/**
 * When pay_period was extracted: green / passed, no approval.
 * When missing: propose 01/current_month/current_year as WARNING (not FAILED)
 * with Requires Approval until the user clicks Approve.
 */
export function applyPayrollPeriodPresentation(options: {
  fields: ExtractedPayslipField[] | undefined;
  drafts: Record<string, FieldDraft>;
  validationMap: Record<string, EmployeeFieldValidationMeta>;
  /** After explicit Approve on the field, proposed period is confirmed. */
  periodApproved: boolean;
  periodCheck?: PeriodCheck | null;
  proposedExplanation: string;
  /** Workspace payroll period — proposal must match this, not calendar "today". */
  workspaceYear?: number;
  workspaceMonth?: number;
  now?: Date;
}): PayrollPeriodPresentation {
  const proposedValue =
    options.workspaceYear != null && options.workspaceMonth != null
      ? proposedPayrollPeriodValue(options.workspaceYear, options.workspaceMonth)
      : proposedPayrollPeriodValue(options.now ?? new Date());
  const displayDrafts = { ...options.drafts };
  const validationMap = { ...options.validationMap };
  const fromField = fieldPayPeriodValue(options.fields);
  const userDraft = options.drafts.pay_period;
  const userEdited = Boolean(userDraft?.dirty && userDraft.value.trim());
  const periodExtracted =
    Boolean(options.periodCheck?.extracted_month && options.periodCheck?.extracted_year) ||
    !isPayPeriodMissing(fromField);

  // Once the period exists on the extraction (or user draft), treat as found.
  // Do not keep a stale local "approved proposal" overlay that forces dirty forever.
  if (periodExtracted) {
    const actual = userEdited ? userDraft!.value.trim() : fromField;
    validationMap.pay_period = {
      status: 'passed',
      labelKey: 'employee.validation.status.passed',
      explanation: null,
      expected: null,
      actual,
      confidencePercent: null,
      requiresApproval: false,
      userApproved: Boolean(options.periodApproved),
    };
    return {
      displayDrafts,
      validationMap,
      requiresApproval: false,
      proposedValue,
    };
  }

  if (options.periodApproved) {
    const value =
      userEdited && userDraft!.value.trim() ? userDraft!.value.trim() : proposedValue;
    // Preserve real draft dirty state (Approve sets dirty once). Never force dirty on
    // every render — that re-queued corrections and unconfirmed the latest extraction.
    displayDrafts.pay_period = {
      value,
      clear: false,
      dirty: Boolean(userDraft?.dirty),
    };
    validationMap.pay_period = {
      status: 'passed',
      labelKey: 'employee.validation.status.passed',
      explanation: null,
      expected: null,
      actual: value,
      confidencePercent: null,
      requiresApproval: false,
      userApproved: true,
    };
    return {
      displayDrafts,
      validationMap,
      requiresApproval: false,
      proposedValue: value,
    };
  }

  // Missing — propose default as WARNING (uncertain), never FAILED.
  const displayValue = userEdited ? userDraft!.value.trim() : proposedValue;
  displayDrafts.pay_period = {
    value: displayValue,
    clear: false,
    dirty: userEdited,
  };
  validationMap.pay_period = {
    status: 'uncertain',
    labelKey: 'employee.validation.status.uncertain',
    explanation: options.proposedExplanation,
    expected: proposedValue,
    actual: null,
    confidencePercent: null,
    requiresApproval: true,
    userApproved: false,
  };

  return {
    displayDrafts,
    validationMap,
    requiresApproval: true,
    proposedValue,
  };
}
