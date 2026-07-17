import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useOptionalUnsavedChanges } from '../features/accountant/UnsavedChangesGuard';
import {
  GuestExtractionSubmission,
  isAbortError,
  mapExtractionFailureMessage,
} from '../lib/guest/guestExtractionAbort';
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

export type EmployeeBusyPhase = 'extracting' | 'confirming' | 'validating' | null;

export type EmployeeReviewTab = 'original' | 'digital';

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
  const extractSubmissionRef = useRef(new GuestExtractionSubmission());
  const validateSubmissionRef = useRef(new GuestExtractionSubmission());

  const [step, setStep] = useState<EmployeeFlowStep>('upload');
  const [busyPhase, setBusyPhase] = useState<EmployeeBusyPhase>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [filePreviewUrl, setFilePreviewUrl] = useState<string | null>(null);
  const [periodYear, setPeriodYear] = useState(initial.year);
  const [periodMonth, setPeriodMonth] = useState(initial.month);
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('auto');
  const [flowError, setFlowError] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<EmployeePayslipExtraction | null>(null);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [report, setReport] = useState<GuestValidationReport | null>(null);
  const [duplicateConflict, setDuplicateConflict] = useState<DuplicateConflict | null>(null);
  const [reviewTab, setReviewTab] = useState<EmployeeReviewTab>('digital');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [acknowledgement, setAcknowledgement] = useState(false);
  const [confirmationStatus, setConfirmationStatus] = useState<string | null>(null);

  const dirty = useMemo(
    () => Object.values(fieldDrafts).some((draft) => draft.dirty),
    [fieldDrafts],
  );

  useEffect(() => {
    unsaved?.setDirty(dirty && step === 'review');
    return () => unsaved?.setDirty(false);
  }, [dirty, step, unsaved]);

  useEffect(() => {
    if (!file) {
      setFilePreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setFilePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    const extractSubmission = extractSubmissionRef.current;
    const validateSubmission = validateSubmissionRef.current;
    return () => {
      extractSubmission.cancel();
      validateSubmission.cancel();
    };
  }, []);

  const identityCheck: IdentityCheck | null = extraction?.identity_check ?? null;
  const periodCheck: PeriodCheck | null = extraction?.period_check ?? null;
  const blocksConfirmation = Boolean(extraction?.blocks_confirmation);
  const isConfirmed = confirmationStatus === 'confirmed';
  const isBusy = busyPhase !== null;

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
      if (isBusy) return;
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
      setAcknowledgement(false);
      setConfirmationStatus(null);
      setStatusMessage(null);
    },
    [file, isBusy, t],
  );

  const removeFile = useCallback(() => {
    if (isBusy) return;
    setFile(null);
    setFileError(null);
  }, [isBusy]);

  const cancelUploadSelection = useCallback(() => {
    if (busyPhase === 'extracting') {
      extractSubmissionRef.current.cancel();
      setBusyPhase(null);
      setStatusMessage(null);
      setStep('upload');
      setFlowError(t('employee.upload.extractionCancelled'));
      return;
    }
    setFile(null);
    setFileError(null);
    setFlowError(null);
    setStatusMessage(null);
  }, [busyPhase, t]);

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

      const signal = extractSubmissionRef.current.begin();
      if (!signal) return;

      setFlowError(null);
      setDuplicateConflict(null);
      setExtraction(null);
      setReport(null);
      setFieldDrafts({});
      setAcknowledgement(false);
      setConfirmationStatus(null);
      setBusyPhase('extracting');
      setStatusMessage(t('employee.upload.extractingDocument'));
      setStep('prepare');
      setReviewTab('digital');

      try {
        const response = await employeePortalService.extractPayslip(file, {
          language: documentLanguage,
          periodYear,
          periodMonth,
          confirmNewVersion,
          signal,
        });
        extractSubmissionRef.current.end();
        setBusyPhase(null);
        setStatusMessage(null);
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
        const intentional = extractSubmissionRef.current.wasIntentionallyCancelled;
        extractSubmissionRef.current.end();
        setBusyPhase(null);
        setStatusMessage(null);

        if (intentional || isAbortError(err)) {
          setFlowError(
            mapExtractionFailureMessage(err, {
              intentionallyCancelled: true,
              cancelledMessage: t('employee.upload.extractionCancelled'),
              fallbackMessage: t('validate.extractionFailed'),
            }),
          );
          setStep('upload');
          return;
        }

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

  const cancelExtraction = useCallback(() => {
    if (busyPhase !== 'extracting') return;
    extractSubmissionRef.current.cancel();
    setBusyPhase(null);
    setStatusMessage(null);
    setStep('upload');
    setFlowError(t('employee.upload.extractionCancelled'));
  }, [busyPhase, t]);

  const confirmDuplicateVersion = useCallback(async () => {
    await runExtract(true);
  }, [runExtract]);

  const persistCorrectionsIfNeeded = useCallback(async (): Promise<EmployeePayslipExtraction | null> => {
    const documentId = extraction?.document_id;
    if (!documentId || !extraction) return null;

    const corrections = Object.entries(fieldDrafts)
      .filter(([, draft]) => draft.dirty)
      .map(([key, draft]) => ({
        key,
        value: draft.clear ? null : parseDraftValue(draft.value),
        clear: draft.clear || draft.value.trim() === '',
      }));

    if (corrections.length === 0) {
      return extraction;
    }

    const latest = await employeePortalService.correctExtraction(documentId, corrections);
    setExtraction(latest);
    initDrafts(latest.fields);
    setConfirmationStatus(null);
    setAcknowledgement(false);
    return latest;
  }, [extraction, fieldDrafts, initDrafts]);

  const confirmExtractedFields = useCallback(async () => {
    const documentId = extraction?.document_id;
    if (!documentId) {
      setFlowError(t('validate.extractionFailed'));
      return;
    }
    if (blocksConfirmation) {
      setFlowError(t('employee.upload.confirmBlocked'));
      return;
    }
    if (!acknowledgement) {
      setFlowError(t('employee.upload.acknowledgementRequired'));
      return;
    }

    setFlowError(null);
    setBusyPhase('confirming');
    setStatusMessage(t('employee.upload.confirming'));
    try {
      const latest = await persistCorrectionsIfNeeded();
      if (latest?.blocks_confirmation) {
        setFlowError(t('employee.upload.confirmBlocked'));
        return;
      }
      const confirmed = await employeePortalService.confirmExtraction(documentId, true);
      setConfirmationStatus(confirmed.confirmation_status);
      unsaved?.setDirty(false);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setFlowError(
          t(`employee.upload.errors.${err.code}`, { defaultValue: err.message }),
        );
        return;
      }
      setFlowError(err instanceof Error ? err.message : t('validate.extractionFailed'));
    } finally {
      setBusyPhase(null);
      setStatusMessage(null);
    }
  }, [
    extraction,
    blocksConfirmation,
    acknowledgement,
    persistCorrectionsIfNeeded,
    unsaved,
    t,
  ]);

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
    if (!isConfirmed) {
      setFlowError(t('employee.upload.confirmBeforeValidate'));
      return;
    }

    const signal = validateSubmissionRef.current.begin();
    if (!signal) return;

    setFlowError(null);
    setBusyPhase('validating');
    setStatusMessage(t('employee.upload.validatingPayroll'));
    setStep('validating');

    try {
      const validation = await employeePortalService.validatePayslip({
        documentId,
        locale,
        signal,
      });
      validateSubmissionRef.current.end();
      setBusyPhase(null);
      setStatusMessage(null);
      setReport(adaptValidationReport(validation, t));
      unsaved?.setDirty(false);
      setReviewTab('digital');
      setStep('report');
    } catch (err) {
      const intentional = validateSubmissionRef.current.wasIntentionallyCancelled;
      validateSubmissionRef.current.end();
      setBusyPhase(null);
      setStatusMessage(null);

      if (intentional || isAbortError(err)) {
        setFlowError(t('employee.upload.validationCancelled'));
        setStep('review');
        return;
      }

      if (err instanceof ApiClientError) {
        if (
          err.code === 'national_id_mismatch' ||
          err.code === 'payroll_period_mismatch' ||
          err.code === 'extraction_not_confirmed'
        ) {
          setFlowError(t(`employee.upload.errors.${err.code}`, { defaultValue: err.message }));
          setStep('review');
          return;
        }
      }
      setFlowError(err instanceof Error ? err.message : t('validate.validationFailed'));
      setStep('review');
    }
  }, [extraction, blocksConfirmation, isConfirmed, locale, unsaved, t]);

  const cancelValidation = useCallback(() => {
    if (busyPhase !== 'validating') return;
    validateSubmissionRef.current.cancel();
    setBusyPhase(null);
    setStatusMessage(null);
    setStep('review');
    setFlowError(t('employee.upload.validationCancelled'));
  }, [busyPhase, t]);

  const reset = useCallback(async () => {
    if (unsaved) {
      const ok = await unsaved.confirmIfDirty();
      if (!ok) return;
    }
    extractSubmissionRef.current.cancel();
    validateSubmissionRef.current.cancel();
    setBusyPhase(null);
    setStatusMessage(null);
    setFile(null);
    setFileError(null);
    setFlowError(null);
    setExtraction(null);
    setFieldDrafts({});
    setReport(null);
    setDuplicateConflict(null);
    setAcknowledgement(false);
    setConfirmationStatus(null);
    setReviewTab('digital');
    setStep('upload');
    setDocumentLanguage('auto');
    const next = nowPeriod();
    setPeriodYear(next.year);
    setPeriodMonth(next.month);
    unsaved?.setDirty(false);
  }, [unsaved]);

  return {
    step,
    busyPhase,
    isBusy,
    statusMessage,
    file,
    fileError,
    filePreviewUrl,
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
    acknowledgement,
    setAcknowledgement,
    confirmationStatus,
    isConfirmed,
    dirty,
    reviewTab,
    setReviewTab,
    selectFile,
    removeFile,
    cancelUploadSelection,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction: () => runExtract(false),
    cancelExtraction,
    confirmDuplicateVersion,
    confirmExtractedFields,
    continueToValidate,
    cancelValidation,
    reset,
  };
}
