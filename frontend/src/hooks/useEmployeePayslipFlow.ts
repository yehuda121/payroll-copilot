import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useOptionalUnsavedChanges } from '../features/accountant/UnsavedChangesGuard';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import { adaptValidationReport } from '../lib/guest/validation-report-adapter';
import { useAppLocale } from './useAppLocale';
import { ApiClientError } from '../services/api';
import {
  employeePortalService,
  type EmployeePayslipExtraction,
  type IdentityCheck,
  type PeriodCheck,
} from '../services/employeePortal';
import type { DocumentLanguage, ExtractedPayslipField } from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';

export type EmployeeFlowStep = 'upload' | 'prepare' | 'review' | 'validating' | 'report';

export type FieldDraft = {
  value: string;
  clear: boolean;
  dirty: boolean;
};

export type DuplicateConflict = {
  existingDocumentId: string;
  existingVersion: number | null;
  uploadedAt: string | null;
};

function serializeFieldValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '';
    }
  }
  return String(value);
}

function parseDraftValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
    return Number(trimmed);
  }
  if (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']'))
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  return trimmed;
}

function nowPeriod(): { year: number; month: number } {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

export function useEmployeePayslipFlow() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const unsaved = useOptionalUnsavedChanges();
  const initial = nowPeriod();

  const [step, setStep] = useState<EmployeeFlowStep>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [periodYear, setPeriodYear] = useState(initial.year);
  const [periodMonth, setPeriodMonth] = useState(initial.month);
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('auto');
  const [flowError, setFlowError] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<EmployeePayslipExtraction | null>(null);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [report, setReport] = useState<GuestValidationReport | null>(null);
  const [duplicateConflict, setDuplicateConflict] = useState<DuplicateConflict | null>(null);

  const dirty = useMemo(
    () => Object.values(fieldDrafts).some((draft) => draft.dirty),
    [fieldDrafts],
  );

  useEffect(() => {
    unsaved?.setDirty(dirty && step === 'review');
    return () => unsaved?.setDirty(false);
  }, [dirty, step, unsaved]);

  const identityCheck: IdentityCheck | null = extraction?.identity_check ?? null;
  const periodCheck: PeriodCheck | null = extraction?.period_check ?? null;
  const blocksConfirmation = Boolean(extraction?.blocks_confirmation);

  const initDrafts = useCallback((fields: ExtractedPayslipField[]) => {
    const next: Record<string, FieldDraft> = {};
    for (const field of fields) {
      next[field.key] = {
        value: serializeFieldValue(field.value),
        clear: false,
        dirty: false,
      };
    }
    setFieldDrafts(next);
  }, []);

  const selectFile = useCallback(
    async (next: File) => {
      const result = await validateUploadFile('payslip', next, file ? [file.name] : [], t);
      if (!result.ok) {
        setFile(next);
        setFileError(result.message);
        return;
      }
      setFile(next);
      setFileError(null);
      setFlowError(null);
      setDuplicateConflict(null);
    },
    [file, t],
  );

  const removeFile = useCallback(() => {
    setFile(null);
    setFileError(null);
  }, []);

  const updateFieldDraft = useCallback((key: string, value: string) => {
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: {
        value,
        clear: value.trim() === '',
        dirty: true,
      },
    }));
  }, []);

  const clearFieldDraft = useCallback((key: string) => {
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: {
        value: '',
        clear: true,
        dirty: true,
      },
    }));
  }, []);

  const runExtract = useCallback(
    async (confirmNewVersion = false) => {
      if (!file) {
        setFlowError(t('employee.upload.payslipRequired'));
        return;
      }
      if (!periodYear || periodMonth < 1 || periodMonth > 12) {
        setFlowError(t('employee.upload.periodRequired'));
        return;
      }

      setFlowError(null);
      setDuplicateConflict(null);
      setExtraction(null);
      setReport(null);
      setFieldDrafts({});
      setStep('prepare');

      try {
        const response = await employeePortalService.extractPayslip(file, {
          language: documentLanguage,
          periodYear,
          periodMonth,
          confirmNewVersion,
        });
        setExtraction(response);
        initDrafts(response.fields);

        if (response.ocr_status === 'failed') {
          setFlowError(response.error_message || t('validate.extractionOcrFailed'));
          setStep('upload');
          return;
        }
        if (response.parser_status === 'failed' && response.fields.length === 0) {
          setFlowError(response.error_message || t('validate.extractionParserFailed'));
          setStep('upload');
          return;
        }
        setStep('review');
      } catch (err) {
        if (err instanceof ApiClientError && err.code === 'duplicate_payslip_period') {
          const details = (err.details || {}) as Record<string, unknown>;
          setDuplicateConflict({
            existingDocumentId: String(details.existing_document_id || ''),
            existingVersion:
              typeof details.existing_version === 'number' ? details.existing_version : null,
            uploadedAt:
              typeof details.uploaded_at === 'string' ? details.uploaded_at : null,
          });
          setFlowError(t('employee.upload.duplicatePeriod'));
          setStep('upload');
          return;
        }
        setFlowError(err instanceof Error ? err.message : t('validate.extractionFailed'));
        setStep('upload');
      }
    },
    [file, periodYear, periodMonth, documentLanguage, initDrafts, t],
  );

  const confirmDuplicateVersion = useCallback(async () => {
    await runExtract(true);
  }, [runExtract]);

  const continueToValidate = useCallback(async () => {
    const documentId = extraction?.document_id;
    if (!documentId) {
      setFlowError(t('validate.extractionFailed'));
      return;
    }
    if (blocksConfirmation) {
      setFlowError(t('employee.upload.confirmBlocked'));
      return;
    }

    setFlowError(null);
    setStep('validating');

    try {
      const corrections = Object.entries(fieldDrafts)
        .filter(([, draft]) => draft.dirty)
        .map(([key, draft]) => ({
          key,
          value: draft.clear ? null : parseDraftValue(draft.value),
          clear: draft.clear || draft.value.trim() === '',
        }));

      let latest = extraction;
      if (corrections.length > 0) {
        latest = await employeePortalService.correctExtraction(documentId, corrections);
        setExtraction(latest);
        initDrafts(latest.fields);
        if (latest.blocks_confirmation) {
          setFlowError(t('employee.upload.confirmBlocked'));
          setStep('review');
          return;
        }
      }

      const validation = await employeePortalService.validatePayslip({
        documentId,
        locale,
      });
      setReport(adaptValidationReport(validation, t));
      unsaved?.setDirty(false);
      setStep('report');
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.code === 'national_id_mismatch' || err.code === 'payroll_period_mismatch') {
          setFlowError(t(`employee.upload.errors.${err.code}`));
          setStep('review');
          return;
        }
      }
      setFlowError(err instanceof Error ? err.message : t('validate.validationFailed'));
      setStep('review');
    }
  }, [extraction, fieldDrafts, blocksConfirmation, locale, initDrafts, unsaved, t]);

  const reset = useCallback(async () => {
    if (unsaved) {
      const ok = await unsaved.confirmIfDirty();
      if (!ok) return;
    }
    setFile(null);
    setFileError(null);
    setFlowError(null);
    setExtraction(null);
    setFieldDrafts({});
    setReport(null);
    setDuplicateConflict(null);
    setStep('upload');
    setDocumentLanguage('auto');
    const next = nowPeriod();
    setPeriodYear(next.year);
    setPeriodMonth(next.month);
    unsaved?.setDirty(false);
  }, [unsaved]);

  return {
    step,
    file,
    fileError,
    periodYear,
    periodMonth,
    setPeriodYear,
    setPeriodMonth,
    documentLanguage,
    setDocumentLanguage,
    flowError,
    extraction,
    fieldDrafts,
    report,
    duplicateConflict,
    identityCheck,
    periodCheck,
    blocksConfirmation,
    selectFile,
    removeFile,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction: () => runExtract(false),
    confirmDuplicateVersion,
    continueToValidate,
    reset,
  };
}
