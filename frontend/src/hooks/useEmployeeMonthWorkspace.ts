import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
import { isNetworkFetchError } from '../lib/getDisplayError';
import {
  type EmployeePayslipExtraction,
  type IdentityCheck,
  type PeriodCheck,
  type PayrollMonthDetail,
} from '../services/employeePortal';
import type { DocumentLanguage, ExtractedPayslipField } from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';
import type { FieldDraft } from './useEmployeePayslipFlow';
import { reviewFieldsFromExtractionPayload } from '../lib/guest/extraction-review';

export type WorkspaceTab =
  | 'upload'
  | 'digital'
  | 'validation'
  | 'employee_checks'
  | 'law_checks'
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

function toUserFacingError(err: unknown, fallback: string, networkFallback?: string): string {
  if (networkFallback && isNetworkFetchError(err)) {
    return networkFallback;
  }
  if (err instanceof ApiClientError) {
    const raw = err.message || '';
    if (
      err.code === 'unsupported_employee_document_type' ||
      /payslip extract endpoint/i.test(raw)
    ) {
      return fallback;
    }
    if (raw.trim()) {
      if (networkFallback && /failed to fetch/i.test(raw)) return networkFallback;
      return raw;
    }
  }
  if (err instanceof Error && err.message.trim()) {
    if (networkFallback && /failed to fetch/i.test(err.message)) return networkFallback;
    return err.message;
  }
  return fallback;
}

function fieldsFromDetail(detail: PayrollMonthDetail): ExtractedPayslipField[] {
  const raw = detail.extraction?.fields ?? [];
  const mapped = raw.map((row) => {
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
  return reviewFieldsFromExtractionPayload({ fields: mapped });
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

export function reportFromMonthDetail(
  detail: PayrollMonthDetail,
  t: (key: string, opts?: Record<string, unknown>) => string,
): GuestValidationReport | null {
  const latest = detail.latest_validation;
  if (!latest?.exists || !latest.validation_run_id) return null;
  const findings = (latest.findings ?? []).map((f) => ({
    id: f.id,
    code: f.code,
    // Prefer authoritative rule_id; fall back to legacy code for older payloads.
    rule_id: (f.rule_id || f.code || '').trim() || f.code,
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
  const ruleOutcomes = (latest.rule_outcomes ?? [])
    .filter((item) => Boolean(item?.rule_id))
    .map((item) => ({
      rule_id: item.rule_id,
      outcome: item.outcome,
      skip_reason: item.skip_reason ?? null,
      reason_code: item.reason_code ?? null,
      message: item.message ?? null,
    }));
  const manualApprovals = (latest.manual_approvals ?? []).map((row) => ({
    finding_id: (row.finding_id as string | null | undefined) ?? null,
    rule_id: (row.rule_id as string | null | undefined) ?? null,
    original_severity: (row.original_severity as string | null | undefined) ?? null,
    original_deterministic_status:
      (row.original_deterministic_status as string | null | undefined) ??
      (row.deterministic_status as string | null | undefined) ??
      null,
    deterministic_status: (row.deterministic_status as string | null | undefined) ?? null,
    review_status: (row.review_status as string | null | undefined) ?? 'manually_approved',
    approved_by: (row.approved_by as string | null | undefined) ?? null,
    approved_at: (row.approved_at as string | null | undefined) ?? null,
    reason: (row.reason as string | null | undefined) ?? null,
    validation_run_id: (row.validation_run_id as string | null | undefined) ?? null,
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
    ruleOutcomes,
    manualApprovals,
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

  const [detail, setDetail] = useState<PayrollMonthDetail | null>(() =>
    session.getPayrollMonthDetail(year, month) ?? null,
  );
  const detailRef = useRef<PayrollMonthDetail | null>(detail);
  detailRef.current = detail;
  const [loading, setLoading] = useState(() => !session.getPayrollMonthDetail(year, month));
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
  const [originalPreviewError, setOriginalPreviewError] = useState<string | null>(null);
  const [originalPreviewLoading, setOriginalPreviewLoading] = useState(false);
  const originalPreviewRequestId = useRef(0);
  const [pendingExtraction, setPendingExtraction] = useState<EmployeePayslipExtraction | null>(null);
  const [previousFieldsForCompare, setPreviousFieldsForCompare] = useState<ExtractedPayslipField[] | null>(
    null,
  );
  const [periodPrompt, setPeriodPrompt] = useState<PeriodCheck | null>(null);

  const isBusy = busyPhase !== null;
  const documentId = extraction?.document_id || detail?.payslip.document_id || null;
  const hasPayslip = Boolean(detail?.payslip.exists || documentId);
  const hasExtraction =
    fields.length > 0 ||
    (busyPhase === 'extracting' && Boolean(detail?.extraction?.exists));
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
      const reviewFields = reviewFieldsFromExtractionPayload(response);
      setFields(reviewFields);
      initDrafts(reviewFields);
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
      setReport((prev) => {
        if (!stored) return null;
        // Prefer hydrated outcomes; if same run briefly lacks them, keep live outcomes.
        if ((stored.ruleOutcomes?.length ?? 0) > 0) return stored;
        if (
          prev &&
          prev.runId === stored.runId &&
          (prev.ruleOutcomes?.length ?? 0) > 0
        ) {
          return {
            ...stored,
            ruleOutcomes: prev.ruleOutcomes,
            manualApprovals: prev.manualApprovals?.length
              ? prev.manualApprovals
              : stored.manualApprovals,
          };
        }
        return stored;
      });
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

      if (opts?.force) {
        session.invalidatePayrollMonth(year, month);
      }

      const cached = opts?.force ? undefined : session.getPayrollMonthDetail(year, month);
      if (cached) {
        applyMonthDetail(cached);
        setLoading(false);
      } else if (!detailRef.current) {
        setLoading(true);
      }

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

  useLayoutEffect(() => {
    const cached = session.getPayrollMonthDetail(year, month);
    if (cached) {
      applyMonthDetail(cached);
      setLoading(false);
    }
  }, [year, month, applyMonthDetail, session]);

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

  // Drop stale server preview when the payslip document changes; keep local pendingFile preview.
  useEffect(() => {
    setOriginalPreviewError(null);
    if (pendingFile) return;
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, [documentId, pendingFile]);

  const ensureOriginalPreview = useCallback(async () => {
    if (pendingFile) return;
    if (!documentId) {
      setOriginalPreviewError(t('employee.upload.originalUnavailable'));
      return;
    }
    if (previewUrl) return;

    const requestId = ++originalPreviewRequestId.current;
    setOriginalPreviewLoading(true);
    setOriginalPreviewError(null);
    try {
      const blob = await workspaceApi.fetchDocumentContentBlob(documentId);
      if (requestId !== originalPreviewRequestId.current) return;
      const url = URL.createObjectURL(blob);
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return url;
      });
    } catch (reason: unknown) {
      if (requestId !== originalPreviewRequestId.current || isAbortError(reason)) return;
      // Scoped to Original Document only — never poison Digital / Checks tabs.
      setOriginalPreviewError(
        toUserFacingError(
          reason,
          t('employee.upload.originalUnavailable'),
          t('common.networkUnavailable'),
        ),
      );
    } finally {
      if (requestId === originalPreviewRequestId.current) {
        setOriginalPreviewLoading(false);
      }
    }
  }, [documentId, pendingFile, previewUrl, t, workspaceApi]);

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
      setOriginalPreviewError(null);
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
    setOriginalPreviewError(null);
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
      setStatusMessage(t('employee.workspace.processing.readingPayslip'));
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
        setError(
          toUserFacingError(err, t('validate.extractionFailed'), t('common.networkUnavailable')),
        );
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
    // Edits invalidate local confirmation — server stays confirmed until corrections
    // persist; validate must go through confirmAndValidate so the latest extraction is
    // re-confirmed (otherwise employee validate hits ExtractionNotConfirmedError).
    setConfirmationStatus((prev) => (prev === 'confirmed' ? 'review_required' : prev));
    setAcknowledgement(false);
    setValidationOutdated(true);
  }, []);

  const clearFieldDraft = useCallback((key: string) => {
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value: '', clear: true, dirty: true },
    }));
    setConfirmationStatus((prev) => (prev === 'confirmed' ? 'review_required' : prev));
    setAcknowledgement(false);
    setValidationOutdated(true);
  }, []);

  const addField = useCallback((payload?: { name: string; value: string }) => {
    const label = payload?.name?.trim() || '';
    const value = payload?.value ?? '';
    const key = label
      ? `custom_field_${label
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '_')
          .replace(/^_|_$/g, '')
          .slice(0, 40)}_${crypto.randomUUID().slice(0, 6)}`
      : `custom_field_${crypto.randomUUID().slice(0, 8)}`;
    setFields((prev) => [
      ...prev,
      {
        key,
        value,
        confidence: null,
        source_text: label || null,
        status: 'FOUND',
        edited_by_user: true,
      },
    ]);
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value, clear: value.trim() === '', dirty: true },
    }));
    setConfirmationStatus((prev) => (prev === 'confirmed' ? 'review_required' : prev));
    setAcknowledgement(false);
    setValidationOutdated(true);
  }, []);

  const removeField = useCallback((key: string) => {
    setFields((prev) => prev.filter((field) => field.key !== key));
    setFieldDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setConfirmationStatus((prev) => (prev === 'confirmed' ? 'review_required' : prev));
    setAcknowledgement(false);
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
        // Apply corrected fields without wiping confirmation mid-flight via applyExtraction.
        // Corrections create review_required on the server until confirm below succeeds.
        setExtraction(latest);
        const reviewFields = reviewFieldsFromExtractionPayload(latest);
        setFields(reviewFields);
        initDrafts(reviewFields);
        setConfirmationStatus('review_required');
        setValidationOutdated(true);
        if (latest.period_check?.status === 'mismatch' && latest.period_check.blocks_confirmation) {
          setPeriodPrompt(latest.period_check);
        } else {
          setPeriodPrompt(null);
        }
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
    initDrafts,
    session,
    year,
    month,
    t,
    workspaceApi,
  ]);

  const runValidation = useCallback(async (
    rerunScope?: 'full' | 'employee_checks' | 'law_checks' | 'rules',
    ruleIds?: string[],
  ) => {
    if (!documentId) {
      setError(t('employee.upload.confirmBeforeValidate'));
      return;
    }
    const signal = validateSubmission.current.begin();
    if (!signal) return;
    setBusyPhase('validating');
    setStatusMessage(
      rerunScope === 'law_checks'
        ? t('employee.workspace.processing.checkingRules', { defaultValue: 'Checking applicable rules…' })
        : rerunScope === 'employee_checks'
          ? t('employee.workspace.processing.comparingEmployee', {
              defaultValue: 'Comparing employee information…',
            })
          : t('employee.workspace.processing.checkingData', { defaultValue: 'Checking payslip data…' }),
    );
    if (rerunScope === 'law_checks') setTab('law_checks');
    else if (rerunScope !== 'rules') setTab('employee_checks');
    try {
      const supporting = detail?.attendance.document_id
        ? [detail.attendance.document_id]
        : [];
      const validation = await workspaceApi.validatePayslip({
        documentId,
        locale,
        supportingDocumentIds: supporting,
        rerunScope: rerunScope ?? 'full',
        ruleIds: ruleIds ?? [],
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
      setError(
        toUserFacingError(err, t('validate.validationFailed'), t('common.networkUnavailable')),
      );
    }
  }, [documentId, detail, locale, refresh, t, workspaceApi]);

  const confirmAndValidate = useCallback(async () => {
    if (!documentId) return;
    if (blocksConfirmation) {
      setError(t('employee.upload.confirmBlocked'));
      setTab('employee_checks');
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

  // User-facing processing copy (not internal pipeline stage names).
  useEffect(() => {
    if (busyPhase !== 'validating' && busyPhase !== 'extracting') return;
    const keys =
      busyPhase === 'extracting'
        ? [
            'employee.workspace.processing.readingPayslip',
            'employee.workspace.processing.preparingResults',
          ]
        : [
            'employee.workspace.processing.checkingData',
            'employee.workspace.processing.comparingEmployee',
            'employee.workspace.processing.checkingRules',
            'employee.workspace.processing.preparingResults',
          ];
    let index = 0;
    setStatusMessage(t(keys[0]));
    const timer = window.setInterval(() => {
      index = (index + 1) % keys.length;
      setStatusMessage(t(keys[index]));
    }, 2800);
    return () => window.clearInterval(timer);
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
      setOriginalPreviewError(null);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setTab('upload');
      await refresh({ force: true });
      return true;
    } catch (err) {
      setError(toUserFacingError(err, t('common.error'), t('common.networkUnavailable')));
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
    originalPreviewError,
    originalPreviewLoading,
    ensureOriginalPreview,
    hasPayslip,
    hasExtraction,
    documentId,
    timelineStep,
    refresh,
  };
}
