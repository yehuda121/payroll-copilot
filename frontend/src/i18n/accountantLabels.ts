/**
 * Accountant portal display-label helpers.
 * Maps domain codes to i18n keys — never translates identifiers in business logic.
 */
import type { TFunction } from 'i18next';

const EMPLOYEE_STATUS_KEYS: Record<string, string> = {
  active: 'accountant.statuses.employee.active',
  on_leave: 'accountant.statuses.employee.onLeave',
  terminated: 'accountant.statuses.employee.terminated',
  disabled: 'accountant.statuses.employee.disabled',
};

const DOCUMENT_STATUS_KEYS: Record<string, string> = {
  available: 'accountant.statuses.document.available',
  missing: 'accountant.statuses.document.missing',
  processing: 'accountant.statuses.document.processing',
  failed: 'accountant.statuses.document.failed',
  needs_review: 'accountant.statuses.document.needsReview',
  versioned: 'accountant.statuses.document.versioned',
};

const BATCH_STATUS_KEYS: Record<string, string> = {
  queued: 'accountant.statuses.batch.queued',
  uploaded: 'accountant.statuses.batch.uploaded',
  splitting: 'accountant.statuses.batch.splitting',
  running: 'accountant.statuses.batch.running',
  extracting: 'accountant.statuses.batch.extracting',
  parsing: 'accountant.statuses.batch.parsing',
  matching: 'accountant.statuses.batch.matching',
  awaiting_review: 'accountant.statuses.batch.awaitingReview',
  validating: 'accountant.statuses.batch.validating',
  completed: 'accountant.statuses.batch.completed',
  completed_with_errors: 'accountant.statuses.batch.completedWithErrors',
  failed: 'accountant.statuses.batch.failed',
  cancelled: 'accountant.statuses.batch.cancelled',
  unknown: 'accountant.statuses.batch.unknown',
};

const BATCH_STAGE_KEYS: Record<string, string> = {
  upload: 'accountant.batches.stages.upload',
  split: 'accountant.batches.stages.split',
  ocr: 'accountant.batches.stages.ocr',
  parser: 'accountant.batches.stages.parser',
  identify: 'accountant.batches.stages.identify',
  validation: 'accountant.batches.stages.validation',
  validate: 'accountant.batches.stages.validation',
  report: 'accountant.batches.stages.report',
};

const STAGE_STATUS_KEYS: Record<string, string> = {
  pending: 'accountant.statuses.stage.pending',
  running: 'accountant.statuses.stage.running',
  completed: 'accountant.statuses.stage.completed',
  failed: 'accountant.statuses.stage.failed',
  skipped: 'accountant.statuses.stage.skipped',
};

const VALIDATION_STATUS_KEYS: Record<string, string> = {
  not_run: 'accountant.statuses.validation.notRun',
  passed: 'accountant.statuses.validation.passed',
  warnings: 'accountant.statuses.validation.warnings',
  warning: 'accountant.statuses.validation.warnings',
  critical: 'accountant.statuses.validation.critical',
  failed: 'accountant.statuses.validation.failed',
  processing: 'accountant.statuses.validation.processing',
  unable_to_verify: 'accountant.statuses.validation.unableToVerify',
};

const EMPLOYMENT_TYPE_KEYS: Record<string, string> = {
  full_time: 'accountant.employees.employmentTypes.fullTime',
  part_time: 'accountant.employees.employmentTypes.partTime',
  contractor: 'accountant.employees.employmentTypes.contractor',
  intern: 'accountant.employees.employmentTypes.intern',
  pre_intern: 'accountant.employees.employmentTypes.preIntern',
};

const SALARY_TYPE_KEYS: Record<string, string> = {
  monthly: 'accountant.employees.salaryTypes.monthly',
  hourly: 'accountant.employees.salaryTypes.hourly',
};

/** Registry: document type code → translation key (UI resolves labels). */
export const DOCUMENT_TYPE_LABEL_KEYS: Record<string, string> = {
  payslip: 'accountant.documents.types.payslip',
  attendance: 'accountant.documents.types.attendance',
  contract: 'accountant.documents.types.employmentContract',
  national_id: 'accountant.documents.types.israeliId',
  id_appendix: 'accountant.documents.types.idAppendix',
};

export const DOCUMENT_COLLECTION_LABEL_KEYS: Record<string, string> = {
  payslips: 'accountant.documents.collections.payslips',
  attendance: 'accountant.documents.collections.attendance',
  contracts: 'accountant.documents.collections.contracts',
  identity: 'accountant.documents.collections.identity',
  documents: 'accountant.documents.collections.documents',
  tax: 'accountant.documents.collections.tax',
};

/** Registry: validation module code → name/description keys. */
export const VALIDATION_MODULE_LABEL_KEYS: Record<
  string,
  { name: string; description: string }
> = {
  payroll: {
    name: 'accountant.validations.modules.payroll.name',
    description: 'accountant.validations.modules.payroll.description',
  },
  attendance: {
    name: 'accountant.validations.modules.attendance.name',
    description: 'accountant.validations.modules.attendance.description',
  },
  contract: {
    name: 'accountant.validations.modules.contract.name',
    description: 'accountant.validations.modules.contract.description',
  },
  tax: {
    name: 'accountant.validations.modules.tax.name',
    description: 'accountant.validations.modules.tax.description',
  },
  pension: {
    name: 'accountant.validations.modules.pension.name',
    description: 'accountant.validations.modules.pension.description',
  },
  company_custom: {
    name: 'accountant.validations.modules.companyCustom.name',
    description: 'accountant.validations.modules.companyCustom.description',
  },
};

function labelFromMap(map: Record<string, string>, code: string, t: TFunction): string {
  const key = map[code];
  if (key) return t(key);
  return t('accountant.statuses.unknown', { code });
}

export function getEmployeeStatusLabel(status: string, t: TFunction): string {
  return labelFromMap(EMPLOYEE_STATUS_KEYS, status, t);
}

export function getDocumentStatusLabel(status: string, t: TFunction): string {
  return labelFromMap(DOCUMENT_STATUS_KEYS, status, t);
}

export function getBatchStatusLabel(status: string, t: TFunction): string {
  return labelFromMap(BATCH_STATUS_KEYS, status, t);
}

export function getBatchStageLabel(stage: string, t: TFunction): string {
  return labelFromMap(BATCH_STAGE_KEYS, stage, t);
}

export function getStageStatusLabel(status: string, t: TFunction): string {
  return labelFromMap(STAGE_STATUS_KEYS, status, t);
}

export function getValidationStatusLabel(status: string, t: TFunction): string {
  return labelFromMap(VALIDATION_STATUS_KEYS, status, t);
}

export function getEmploymentTypeLabel(type: string, t: TFunction): string {
  return labelFromMap(EMPLOYMENT_TYPE_KEYS, type, t);
}

export function getSalaryTypeLabel(type: string, t: TFunction): string {
  return labelFromMap(SALARY_TYPE_KEYS, type, t);
}

export function getDocumentTypeLabel(typeKey: string, t: TFunction): string {
  const key = DOCUMENT_TYPE_LABEL_KEYS[typeKey] ?? `accountant.documents.types.${typeKey}`;
  return t(key);
}

export function getDocumentCollectionLabel(collectionKey: string, t: TFunction): string {
  const key =
    DOCUMENT_COLLECTION_LABEL_KEYS[collectionKey] ??
    `accountant.documents.collections.${collectionKey}`;
  return t(key);
}

export function getValidationModuleName(moduleKey: string, t: TFunction): string {
  const entry = VALIDATION_MODULE_LABEL_KEYS[moduleKey];
  if (entry) return t(entry.name);
  return t('accountant.validations.modules.unknown.name', { code: moduleKey });
}

export function getValidationModuleDescription(moduleKey: string, t: TFunction): string {
  const entry = VALIDATION_MODULE_LABEL_KEYS[moduleKey];
  if (entry) return t(entry.description);
  return t('accountant.validations.modules.unknown.description', { code: moduleKey });
}

/** Map known API/user-safe error situations to translation keys. */
export function getAccountantErrorMessage(
  code:
    | 'loadFailed'
    | 'saveFailed'
    | 'uploadFailed'
    | 'matchFailed'
    | 'disableFailed'
    | 'generic',
  t: TFunction,
): string {
  return t(`accountant.errors.${code}`);
}
