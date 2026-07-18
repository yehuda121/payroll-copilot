import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useEmployeeSession } from '../auth/EmployeeSessionContext';
import { useEmployeeWorkspace } from '../features/employee/EmployeeWorkspaceContext';
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
  type EmployeePayslipExtraction,
  type IdentityCheck,
  type PeriodCheck,
  type PayrollMonthDetail,
} from '../services/employeePortal';
import type { DocumentLanguage, ExtractedPayslipField } from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';
import type { FieldDraft } from './useEmployeePayslipFlow';

export type WorkspaceTab =
  | 'upload'
  | 'digital'
  | 'validation'
  | 'original'
  | 'chat'
  | 'publishing';
export type BusyPhase = 'uploading' | 'extracting' | 'confirming' | 'validating' | null;

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
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

function toUserFacingError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    const raw = err.message || '';
    if (
      err.code === 'unsupported_employee_document_type' ||
      /payslip extract endpoint/i.test(raw)
    ) {
      return fallback;
    }
    if (raw.trim()) return raw;
  }
  if (err instanceof Error && err.message.trim()) return err.message;
  return fallback;
}

function fieldsFromDetail(detail: PayrollMonthDetail): ExtractedPayslipField[] {
  const raw = detail.extraction?.fields ?? [];
  return raw.map((row) => {
    const record = row as Record<string, unknown>;
    const value =
      record.value !== undefined
        ? record.value
        : record.effective_value !== undefined
          ? record.effective_value
          : null;
    return {
      key: String(record.key ?? ''),
      value,
      confidence: typeof record.confidence === 'number' ? record.confidence : null,
      source_text: typeof record.source_text === 'string' ? record.source_text : null,
      status: String(record.status ?? record.extraction_status ?? 'MISSING'),
      edited_by_user: Boolean(record.edited_by_user ?? record.edited_by_employee),
    };
  });
}

function extractionFromDetail(
  detail: PayrollMonthDetail,
  fields: ExtractedPayslipField[],
): EmployeePayslipExtraction | null {
  const ext = detail.extraction;
  const documentId = detail.payslip.document_id;
  if (!ext?.exists || !documentId || fields.length === 0) return null;
  if (!ext.identity_check || !ext.period_check) return null;
  return {
    document_id: documentId,
    extraction_id: String(ext.extraction_id || ''),
    extraction_version: ext.extraction_version ?? null,
    ocr_status: 'completed',
    parser_status: 'completed',
    language: 'he',
    warnings: [],
    fields,
    error_message: null,
    identity_check: ext.identity_check,
    period_check: ext.period_check,
    blocks_confirmation: Boolean(ext.blocks_confirmation),
  };
}

function reportFromMonthDetail(
  detail: PayrollMonthDetail,
  t: (key: string, opts?: Record<string, unknown>) => string,
): GuestValidationReport | null {
  const latest = detail.latest_validation;
  if (!latest?.exists || !latest.validation_run_id) return null;
  const findings = (latest.findings ?? []).map((f) => ({
    id: f.id,
    code: f.code,
    rule_id: f.code,
    severity: (f.severity as 'info' | 'warning' | 'critical') || 'info',
    message_key: f.message_key,
    // Keep message_key for mapping; never surface raw keys as display message.
    message: '',
    explanation:
      f.explanation && !/^[a-z][a-z0-9_.-]*$/i.test(f.explanation)
        ? f.explanation
        : typeof f.message_params?.explanation === 'string' &&
            !/^[a-z][a-z0-9_.-]*$/i.test(String(f.message_params.explanation))
          ? String(f.message_params.explanation)
          : '',
    expected_value: f.expected_value ?? null,
    actual_value: f.actual_value ?? null,
    confidence: f.confidence ?? 0,
    legal_reference: f.legal_reference ?? null,
  }));
  return {
    runId: latest.validation_run_id,
    documentId: detail.payslip.document_id || '',
    overallResult: (latest.overall_result as GuestValidationReport['overallResult']) ?? null,
    overallStatus: String(latest.overall_result || latest.status || ''),
    summary: latest.completed_at
      ? `${t('employee.workspace.storedValidationSummary')} ${t(
          'employee.validation.completedAt',
          { at: latest.completed_at },
        )}`
      : t('employee.workspace.storedValidationSummary'),
    validationConfidence: latest.confidence,
    confidenceExplanation: latest.confidence_explanation ?? null,
    scope: (latest.scope ?? []).map((item) => ({
      key: item.key,
      label: item.label,
      status: (['completed', 'partial', 'not_available'].includes(item.status)
        ? item.status
        : 'not_available') as 'completed' | 'partial' | 'not_available',
      reason: item.reason ?? null,
    })),
    uploadedDocuments: [],
    checksPassedCount: Math.max(0, (latest.findings_count ?? 0) === 0 ? 1 : 0),
    findings,
    extractionConnected: Boolean(detail.extraction?.exists),
  };
}

export function useEmployeeMonthWorkspace(year: number, month: number) {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const navigate = useNavigate();
  const { api: workspaceApi, basePath } = useEmployeeWorkspace();
  const session = useEmployeeSession();
  const uploadSubmission = useRef(new GuestExtractionSubmission());
  const extractSubmission = useRef(new GuestExtractionSubmission());
  const validateSubmission = useRef(new GuestExtractionSubmission());

  const [detail, setDetail] = useState<PayrollMonthDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyPhase, setBusyPhase] = useState<BusyPhase>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [tab, setTab] = useState<WorkspaceTab>('upload');
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('he');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<EmployeePayslipExtraction | null>(null);
  const [fields, setFields] = useState<ExtractedPayslipField[]>([]);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [acknowledgement, setAcknowledgement] = useState(false);
  const [confirmationStatus, setConfirmationStatus] = useState<string | null>(null);
  const [report, setReport] = useState<GuestValidationReport | null>(null);
  const [validationOutdated, setValidationOutdated] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [pendingExtraction, setPendingExtraction] = useState<EmployeePayslipExtraction | null>(null);
  const [previousFieldsForCompare, setPreviousFieldsForCompare] = useState<ExtractedPayslipField[] | null>(
    null,
  );
  const [periodPrompt, setPeriodPrompt] = useState<PeriodCheck | null>(null);

  const isBusy = busyPhase !== null;
  const documentId = extraction?.document_id || detail?.payslip.document_id || null;
  const hasPayslip = Boolean(detail?.payslip.exists || documentId);
  const hasExtraction = fields.length > 0 || Boolean(detail?.extraction?.exists && detail.extraction.fields.length);
  const isConfirmed = confirmationStatus === 'confirmed';
  const blocksConfirmation = Boolean(extraction?.blocks_confirmation);
  const identityCheck: IdentityCheck | null = extraction?.identity_check ?? null;
  const periodCheck: PeriodCheck | null = extraction?.period_check ?? null;

  const dirty = useMemo(
    () => Object.values(fieldDrafts).some((draft) => draft.dirty),
    [fieldDrafts],
  );

  const initDrafts = useCallback((nextFields: ExtractedPayslipField[]) => {
    const next: Record<string, FieldDraft> = {};
    for (const field of nextFields) {
      next[field.key] = {
        value: serializeFieldValue(field.value),
        clear: false,
        dirty: false,
      };
    }
    setFieldDrafts(next);
  }, []);

  const applyExtraction = useCallback(
    (response: EmployeePayslipExtraction) => {
      setExtraction(response);
      setFields(response.fields);
      initDrafts(response.fields);
      setConfirmationStatus(null);
      setAcknowledgement(false);
      setValidationOutdated(true);
      setReport(null);
      if (response.period_check?.status === 'mismatch' && response.period_check.blocks_confirmation) {
        setPeriodPrompt(response.period_check);
      } else {
        setPeriodPrompt(null);
      }
      setTab('digital');
    },
    [initDrafts],
  );

  const applyMonthDetail = useCallback(
    (row: PayrollMonthDetail) => {
      setDetail(row);
      const nextFields = fieldsFromDetail(row);
      if (nextFields.length > 0) {
        setFields(nextFields);
        initDrafts(nextFields);
      }
      const restored = extractionFromDetail(row, nextFields);
      setExtraction(restored);
      const period = restored?.period_check ?? row.extraction?.period_check ?? null;
      if (
        period &&
        period.status === 'mismatch' &&
        period.blocks_confirmation &&
        row.extraction?.confirmation_status !== 'confirmed'
      ) {
        setPeriodPrompt(period);
      } else {
        setPeriodPrompt(null);
      }
      const confirmation = row.extraction?.confirmation_status ?? null;
      setConfirmationStatus(confirmation);
      setAcknowledgement(confirmation === 'confirmed');
      const stored = reportFromMonthDetail(row, t);
      setReport(stored);
      setValidationOutdated(Boolean(row.latest_validation.outdated));
      if (!row.payslip.document_id) {
        setPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        setFields([]);
        setFieldDrafts({});
        setExtraction(null);
        setReport(null);
        setConfirmationStatus(null);
        setAcknowledgement(false);
        setPeriodPrompt(null);
      }
    },
    [initDrafts, t],
  );

  const refresh = useCallback(
    async (opts?: { force?: boolean }) => {
      setError(null);

      if (!opts?.force) {
        const cached = session.getPayrollMonthDetail(year, month);
        if (cached) {
          applyMonthDetail(cached);
          setLoading(false);
          return;
        }
      } else {
        session.invalidatePayrollMonth(year, month);
      }

      setLoading(true);
      try {
        const row = await workspaceApi.getPayrollMonthDetail(year, month);
        session.setPayrollMonthDetail(row);
        applyMonthDetail(row);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('common.error'));
      } finally {
        setLoading(false);
      }
    },
    [year, month, applyMonthDetail, session, t, workspaceApi],
  );

  useEffect(() => {
    void refresh();
    return () => {
      uploadSubmission.current.cancel();
      extractSubmission.current.cancel();
      validateSubmission.current.cancel();
    };
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    if (!documentId || pendingFile) return;
    const controller = new AbortController();
    void workspaceApi
      .fetchDocumentContentBlob(documentId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        setPreviewUrl((previous) => {
          if (previous) URL.revokeObjectURL(previous);
          return url;
        });
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted && !isAbortError(reason)) {
          setError(toUserFacingError(reason, t('employee.upload.originalUnavailable')));
        }
      });
    return () => controller.abort();
  }, [documentId, pendingFile, t, workspaceApi]);

  const selectFile = useCallback(
    async (file: File) => {
      if (isBusy) return;
      const result = await validateUploadFile('payslip', file, [], t);
      if (!result.ok) {
        setPendingFile(file);
        setFileError(result.message);
        return;
      }
      setPendingFile(file);
      setFileError(null);
      setError(null);
      const url = URL.createObjectURL(file);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    },
    [isBusy, t],
  );

  const deleteSelectedFile = useCallback(() => {
    if (busyPhase === 'uploading' || busyPhase === 'extracting') {
      uploadSubmission.current.cancel();
      extractSubmission.current.cancel();
      setBusyPhase(null);
      setStatusMessage(null);
    }
    setPendingFile(null);
    setFileError(null);
    setError(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, [busyPhase]);

  const runExtract = useCallback(
    async (opts?: { confirmNewVersion?: boolean; forCompare?: boolean }) => {
      if (!opts?.forCompare && !pendingFile && !documentId) {
        setError(t('employee.upload.payslipRequired'));
        return;
      }

      const signal = extractSubmission.current.begin();
      if (!signal) return;

      setTab('digital');
      setBusyPhase('extracting');
      setStatusMessage(t('employee.workspace.extractingStatus'));
      setError(null);
      try {
        if (opts?.forCompare && fields.length > 0) {
          setPreviousFieldsForCompare(fields);
        }
        const useFile = Boolean(pendingFile) && !opts?.forCompare;
        const useDocId = Boolean(documentId) && (!pendingFile || Boolean(opts?.forCompare));
        const response = await workspaceApi.extractPayslip(useFile ? pendingFile : null, {
          language: documentLanguage,
          periodYear: year,
          periodMonth: month,
          confirmNewVersion:
            Boolean(opts?.confirmNewVersion) || Boolean(documentId && opts?.forCompare),
          documentId: useDocId ? documentId || undefined : undefined,
          signal,
        });
        extractSubmission.current.end();
        setBusyPhase(null);
        setStatusMessage(null);
        setPendingFile(null);
        if (opts?.forCompare) {
          setPendingExtraction(response);
          session.invalidatePayrollMonth(year, month);
          return;
        }
        applyExtraction(response);
        await refresh({ force: true });
      } catch (err) {
        const intentional = extractSubmission.current.wasIntentionallyCancelled;
        extractSubmission.current.end();
        setBusyPhase(null);
        setStatusMessage(null);
        if (intentional || isAbortError(err)) {
          setError(
            mapExtractionFailureMessage(err, {
              intentionallyCancelled: true,
              cancelledMessage: t('employee.upload.extractionCancelled'),
              fallbackMessage: t('validate.extractionFailed'),
            }),
          );
          return;
        }
        if (err instanceof ApiClientError && err.code === 'duplicate_payslip_period') {
          setError(t('employee.upload.duplicatePeriod'));
          return;
        }
        setError(toUserFacingError(err, t('validate.extractionFailed')));
        await refresh({ force: true });
      }
    },
    [
      pendingFile,
      documentId,
      documentLanguage,
      year,
      month,
      fields,
      applyExtraction,
      refresh,
      session,
      t,
      workspaceApi,
    ],
  );

  const cancelExtraction = useCallback(() => {
    if (busyPhase !== 'extracting') return;
    extractSubmission.current.cancel();
    setBusyPhase(null);
    setStatusMessage(null);
    setError(t('employee.upload.extractionCancelled'));
  }, [busyPhase, t]);

  const acceptPendingExtraction = useCallback(() => {
    if (!pendingExtraction) return;
    applyExtraction(pendingExtraction);
    setPendingExtraction(null);
    setPreviousFieldsForCompare(null);
    void refresh({ force: true });
  }, [pendingExtraction, applyExtraction, refresh]);

  const cancelPendingExtraction = useCallback(() => {
    setPendingExtraction(null);
    if (previousFieldsForCompare) {
      setFields(previousFieldsForCompare);
      initDrafts(previousFieldsForCompare);
    }
    setPreviousFieldsForCompare(null);
  }, [previousFieldsForCompare, initDrafts]);

  const updateFieldDraft = useCallback((key: string, value: string) => {
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value, clear: value.trim() === '', dirty: true },
    }));
    setValidationOutdated(true);
  }, []);

  const clearFieldDraft = useCallback((key: string) => {
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value: '', clear: true, dirty: true },
    }));
    setValidationOutdated(true);
  }, []);

  const addField = useCallback(() => {
    const key = `custom_field_${crypto.randomUUID().slice(0, 8)}`;
    setFields((prev) => [
      ...prev,
      {
        key,
        value: '',
        confidence: null,
        source_text: null,
        status: 'FOUND',
        edited_by_user: true,
      },
    ]);
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value: '', clear: false, dirty: true },
    }));
    setValidationOutdated(true);
  }, []);

  const removeField = useCallback((key: string) => {
    setFields((prev) => prev.filter((field) => field.key !== key));
    setFieldDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setValidationOutdated(true);
  }, []);

  const confirmExtractedFields = useCallback(async () => {
    if (!documentId) return false;
    if (blocksConfirmation) {
      setError(t('employee.upload.confirmBlocked'));
      return false;
    }
    setBusyPhase('confirming');
    setStatusMessage(t('employee.upload.confirming'));
    setAcknowledgement(true);
    try {
      const corrections = Object.entries(fieldDrafts)
        .filter(([, draft]) => draft.dirty)
        .map(([key, draft]) => ({
          key,
          value: draft.clear ? null : parseDraftValue(draft.value),
          clear: draft.clear || draft.value.trim() === '',
        }));
      if (corrections.length > 0) {
        const latest = await workspaceApi.correctExtraction(documentId, corrections);
        applyExtraction(latest);
      }
      const confirmed = await workspaceApi.confirmExtraction(documentId, true);
      setConfirmationStatus(confirmed.confirmation_status);
      setValidationOutdated(true);
      // Server state changed; drop cached month so the next open refetches.
      session.invalidatePayrollMonth(year, month);
      return confirmed.confirmation_status === 'confirmed';
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(t(`employee.upload.errors.${err.code}`, { defaultValue: err.message }));
      } else {
        setError(err instanceof Error ? err.message : t('common.error'));
      }
      return false;
    } finally {
      setBusyPhase(null);
      setStatusMessage(null);
    }
  }, [
    documentId,
    blocksConfirmation,
    fieldDrafts,
    applyExtraction,
    session,
    year,
    month,
    t,
    workspaceApi,
  ]);

  const runValidation = useCallback(async () => {
    if (!documentId) {
      setError(t('employee.upload.confirmBeforeValidate'));
      return;
    }
    const signal = validateSubmission.current.begin();
    if (!signal) return;
    setBusyPhase('validating');
    setStatusMessage(t('employee.upload.validatingPayroll'));
    setTab('validation');
    try {
      const supporting = detail?.attendance.document_id
        ? [detail.attendance.document_id]
        : [];
      const validation = await workspaceApi.validatePayslip({
        documentId,
        locale,
        supportingDocumentIds: supporting,
        signal,
      });
      validateSubmission.current.end();
      setBusyPhase(null);
      setStatusMessage(null);
      setReport(adaptValidationReport(validation, t));
      setValidationOutdated(false);
      setFieldDrafts((prev) => {
        const next: Record<string, FieldDraft> = {};
        for (const [key, draft] of Object.entries(prev)) {
          next[key] = { ...draft, dirty: false };
        }
        return next;
      });
      await refresh({ force: true });
    } catch (err) {
      const intentional = validateSubmission.current.wasIntentionallyCancelled;
      validateSubmission.current.end();
      setBusyPhase(null);
      setStatusMessage(null);
      if (intentional || isAbortError(err)) {
        setError(t('employee.upload.validationCancelled'));
        return;
      }
      setError(toUserFacingError(err, t('validate.validationFailed')));
    }
  }, [documentId, detail, locale, refresh, t, workspaceApi]);

  const confirmAndValidate = useCallback(async () => {
    if (!documentId) return;
    if (blocksConfirmation) {
      setError(t('employee.upload.confirmBlocked'));
      setTab('validation');
      return;
    }
    const ok = await confirmExtractedFields();
    if (!ok) return;
    await runValidation();
  }, [documentId, blocksConfirmation, confirmExtractedFields, runValidation, t]);

  const cancelValidation = useCallback(() => {
    if (busyPhase !== 'validating') return;
    validateSubmission.current.cancel();
    setBusyPhase(null);
    setStatusMessage(null);
    setError(t('employee.upload.validationCancelled'));
  }, [busyPhase, t]);

  const resolvePeriod = useCallback(
    async (action: 'keep' | 'move' | 'cancel') => {
      if (!documentId) return;
      try {
        const result = await workspaceApi.resolvePayslipPeriod(documentId, action);
        setPeriodPrompt(null);
        if (action === 'move' && result.period_year && result.period_month) {
          navigate(`${basePath}/payslips/${result.period_year}/${result.period_month}`);
          return;
        }
        if (action === 'keep') {
          setExtraction((prev) =>
            prev
              ? {
                  ...prev,
                  blocks_confirmation: Boolean(prev.identity_check.blocks_confirmation),
                  period_check: {
                    ...prev.period_check,
                    blocks_confirmation: false,
                    explanation_code: 'period_kept_selected',
                  },
                }
              : prev,
          );
        }
        await refresh({ force: true });
      } catch (err) {
        setError(err instanceof Error ? err.message : t('common.error'));
      }
    },
    [basePath, documentId, navigate, refresh, t, workspaceApi],
  );

  const deleteOwnedDocument = useCallback(async () => {
    if (!documentId) return false;
    setBusyPhase('uploading');
    setStatusMessage(t('employee.workspace.deletingDocument'));
    setError(null);
    try {
      await workspaceApi.deleteOwnedDocument(documentId);
      setExtraction(null);
      setFields([]);
      setFieldDrafts({});
      setReport(null);
      setConfirmationStatus(null);
      setAcknowledgement(false);
      setPeriodPrompt(null);
      setPendingExtraction(null);
      setPendingFile(null);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setTab('upload');
      await refresh({ force: true });
      return true;
    } catch (err) {
      setError(toUserFacingError(err, t('common.error')));
      return false;
    } finally {
      setBusyPhase(null);
      setStatusMessage(null);
    }
  }, [documentId, refresh, t, workspaceApi]);

  const timelineStep = useMemo(() => {
    if (report && !validationOutdated) return 'completed';
    if (isConfirmed || busyPhase === 'validating') return 'validation';
    if (hasExtraction || busyPhase === 'extracting') return 'review';
    if (hasPayslip || busyPhase === 'uploading') return 'extraction';
    return 'upload';
  }, [report, validationOutdated, isConfirmed, busyPhase, hasExtraction, hasPayslip]);

  return {
    detail,
    loading,
    error,
    busyPhase,
    isBusy,
    statusMessage,
    tab,
    setTab,
    documentLanguage,
    setDocumentLanguage,
    pendingFile,
    fileError,
    selectFile,
    deleteSelectedFile,
    canExtract:
      (Boolean(pendingFile) && !fileError) || (Boolean(documentId) && !hasExtraction),
    runExtract: () => runExtract(),
    replaceDocument: () => runExtract({ confirmNewVersion: true }),
    extractAgain: () => runExtract({ confirmNewVersion: true, forCompare: true }),
    cancelExtraction,
    pendingExtraction,
    previousFieldsForCompare,
    acceptPendingExtraction,
    cancelPendingExtraction,
    fields,
    fieldDrafts,
    updateFieldDraft,
    clearFieldDraft,
    addField,
    removeField,
    dirty,
    acknowledgement,
    setAcknowledgement,
    isConfirmed,
    blocksConfirmation,
    identityCheck,
    periodCheck,
    periodPrompt,
    resolvePeriod,
    confirmExtractedFields,
    confirmAndValidate,
    runValidation,
    cancelValidation,
    deleteOwnedDocument,
    report,
    validationOutdated,
    previewUrl,
    hasPayslip,
    hasExtraction,
    documentId,
    timelineStep,
    refresh,
  };
}
