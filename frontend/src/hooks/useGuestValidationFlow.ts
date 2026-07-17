import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { GuestDocumentSlotId } from '../lib/guest/document-slots';
import {
  GuestExtractionSubmission,
  mapExtractionFailureMessage,
} from '../lib/guest/guestExtractionAbort';
import { clearGuestSession } from '../lib/guest/guest-session';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import {
  createBlankEntry,
  entriesFromExtractionResponse,
  hasUsableDynamicEntries,
  parseEntryValue,
} from '../lib/guest/extraction-review';
import { adaptValidationReport } from '../lib/guest/validation-report-adapter';
import { useAppLocale } from './useAppLocale';
import { authService } from '../services/auth';
import { extractionService } from '../services/extraction';
import { validationService } from '../services/validation';
import type {
  DocumentLanguage,
  DynamicDocumentEntry,
  GuestPayslipExtractionResponse,
} from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';

export type UploadSlotState = {
  file: File;
  documentId?: string;
  error?: string;
};

export type ValidationFlowStep = 'upload' | 'prepare' | 'review' | 'validating' | 'report';

export type ExtractionProcessingStage =
  | 'reading_pdf'
  | 'running_ocr'
  | 'structuring_fields'
  | 'preparing_review'
  | null;

/** @deprecated Kept for ValidationWizard compatibility. */
export type FieldDraft = {
  value: string;
  clear: boolean;
  dirty: boolean;
};

export function useGuestValidationFlow() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [step, setStep] = useState<ValidationFlowStep>('upload');
  const [slots, setSlots] = useState<Partial<Record<GuestDocumentSlotId, UploadSlotState>>>({});
  const [flowError, setFlowError] = useState<string | null>(null);
  const [report, setReport] = useState<GuestValidationReport | null>(null);
  const [extraction, setExtraction] = useState<GuestPayslipExtractionResponse | null>(null);
  const [entries, setEntries] = useState<DynamicDocumentEntry[]>([]);
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('auto');
  const [processingStage, setProcessingStage] = useState<ExtractionProcessingStage>(null);
  const submissionRef = useRef(new GuestExtractionSubmission());
  const slotsRef = useRef(slots);
  slotsRef.current = slots;

  const selectedNames = useMemo(
    () => Object.values(slots).map((slot) => slot?.file.name).filter(Boolean) as string[],
    [slots],
  );

  const isBusy = step === 'prepare' || step === 'validating';

  const selectFile = useCallback(
    async (slotId: GuestDocumentSlotId, file: File) => {
      const result = await validateUploadFile(slotId, file, selectedNames, t);
      if (!result.ok) {
        setSlots((prev) => ({
          ...prev,
          [slotId]: { file, error: result.message },
        }));
        return false;
      }
      setSlots((prev) => ({ ...prev, [slotId]: { file } }));
      setFlowError(null);
      return true;
    },
    [selectedNames, t],
  );

  const removeFile = useCallback((slotId: GuestDocumentSlotId) => {
    setSlots((prev) => {
      const next = { ...prev };
      delete next[slotId];
      return next;
    });
  }, []);

  const updateEntry = useCallback(
    (id: string, patch: Partial<Pick<DynamicDocumentEntry, 'key' | 'value'>>) => {
      setEntries((prev) =>
        prev.map((entry) => {
          if (entry.id !== id) return entry;
          const next: DynamicDocumentEntry = { ...entry, source: 'user' };
          if (patch.key !== undefined) next.key = patch.key;
          if (patch.value !== undefined) {
            next.value =
              typeof patch.value === 'string' ? parseEntryValue(patch.value) : patch.value;
          }
          return next;
        }),
      );
    },
    [],
  );

  const deleteEntry = useCallback((id: string) => {
    setEntries((prev) => prev.filter((entry) => entry.id !== id));
  }, []);

  const addEntry = useCallback(() => {
    setEntries((prev) => [...prev, createBlankEntry()]);
  }, []);

  const startExtraction = useCallback(async (payslipOverride?: File): Promise<string | null> => {
    const payslip = payslipOverride ?? slotsRef.current.payslip?.file;
    if (!payslip) {
      setFlowError(t('validate.payslipRequired'));
      return null;
    }

    const submission = submissionRef.current;
    const signal = submission.begin();
    if (!signal) return null;

    setFlowError(null);
    setExtraction(null);
    setReport(null);
    setEntries([]);
    setStep('prepare');
    setProcessingStage('reading_pdf');
    setSlots((prev) => ({
      ...prev,
      payslip: { file: payslip, error: prev.payslip?.error },
    }));

    try {
      await authService.createGuestSession();
      setProcessingStage('running_ocr');

      const extractionResponse = await extractionService.extractGuestPayslip(
        payslip,
        documentLanguage,
        signal,
      );
      if (signal.aborted) {
        throw new DOMException('Extraction cancelled.', 'AbortError');
      }
      setProcessingStage('structuring_fields');
      setExtraction(extractionResponse);
      // Document-origin entries only — never synthesize empty canonical schema rows.
      const nextEntries = entriesFromExtractionResponse(extractionResponse);
      setEntries(nextEntries);
      setSlots((prev) => ({
        ...prev,
        payslip: {
          file: payslip,
          documentId: extractionResponse.document_id,
          error: prev.payslip?.error,
        },
      }));

      if (extractionResponse.ocr_status === 'failed') {
        setFlowError(extractionResponse.error_message || t('validate.extractionOcrFailed'));
        setStep('upload');
        setProcessingStage(null);
        return null;
      }

      if (extractionResponse.parser_status === 'failed' || !hasUsableDynamicEntries(nextEntries)) {
        setFlowError(
          extractionResponse.error_message ||
            t('landingChat.extractionEmpty', {
              defaultValue: 'We could not extract usable information from this document.',
            }),
        );
        setStep('upload');
        setProcessingStage(null);
        return null;
      }

      setProcessingStage('preparing_review');
      setStep('review');
      setProcessingStage(null);
      return extractionResponse.document_id;
    } catch (err) {
      setFlowError(
        mapExtractionFailureMessage(err, {
          intentionallyCancelled: submission.wasIntentionallyCancelled,
          cancelledMessage: t('landingChat.extractionCancelled', {
            defaultValue: 'Extraction cancelled.',
          }),
          fallbackMessage: t('validate.extractionFailed'),
        }),
      );
      setStep('upload');
      setProcessingStage(null);
      return null;
    } finally {
      submission.end();
    }
  }, [documentLanguage, t]);

  const storeSupportingFiles = useCallback(
    async (
      files: Array<{ slotId: GuestDocumentSlotId; file: File }>,
      payslipDocumentId?: string,
    ) => {
      for (const item of files) {
        if (item.slotId !== 'national_id' && item.slotId !== 'contract') {
          setSlots((prev) => ({
            ...prev,
            [item.slotId]: { file: item.file, error: prev[item.slotId]?.error },
          }));
          continue;
        }
        const uploaded = await extractionService.uploadGuestSupporting(
          item.file,
          item.slotId,
          payslipDocumentId,
        );
        setSlots((prev) => ({
          ...prev,
          [item.slotId]: {
            file: item.file,
            documentId: uploaded.document_id,
            error: prev[item.slotId]?.error,
          },
        }));
      }
    },
    [],
  );

  const cancelExtraction = useCallback(() => {
    submissionRef.current.cancel();
    setProcessingStage(null);
    setStep('upload');
    setFlowError(t('landingChat.extractionCancelled', { defaultValue: 'Extraction cancelled.' }));
  }, [t]);

  /**
   * Confirm reviewed document (edits optional) → canonical mapping → validation.
   * Does not require a prior /corrections call — confirm accepts the entries snapshot.
   */
  const continueToValidate = useCallback(async () => {
    if (submissionRef.current.isBusy || step === 'validating') return;
    const documentId = slots.payslip?.documentId || extraction?.document_id;
    if (!documentId) {
      setFlowError(t('validate.extractionFailed'));
      return;
    }

    if (!hasUsableDynamicEntries(entries)) {
      setFlowError(
        t('landingChat.confirmBlockedEmpty', {
          defaultValue: 'Add or correct at least one field before confirming.',
        }),
      );
      setStep('review');
      return;
    }

    setFlowError(null);
    setStep('validating');

    try {
      // Corrections are optional. Confirm alone freezes the reviewed entries for mapping.
      await extractionService.confirmGuestExtraction(documentId, entries);

      const supportingIds = Object.entries(slots)
        .filter(([slotId, slot]) => slotId !== 'payslip' && Boolean(slot?.documentId))
        .map(([, slot]) => slot!.documentId!) as string[];

      const validation = await validationService.runValidation({
        document_id: documentId,
        supporting_document_ids: supportingIds,
        locale,
      });

      setReport(adaptValidationReport(validation, t));
      setStep('report');
    } catch (err) {
      setFlowError(err instanceof Error ? err.message : t('validate.validationFailed'));
      setStep('review');
    }
  }, [slots, extraction, entries, locale, t, step]);

  const reset = useCallback(() => {
    submissionRef.current.cancel();
    clearGuestSession();
    setSlots({});
    setReport(null);
    setExtraction(null);
    setEntries([]);
    setFlowError(null);
    setStep('upload');
    setProcessingStage(null);
    setDocumentLanguage('auto');
  }, []);

  useEffect(() => {
    const submission = submissionRef.current;
    const onBeforeUnload = () => {
      submission.cancel();
      clearGuestSession();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      submission.cancel();
    };
  }, []);

  // Compatibility stubs for ValidationWizard (schema-era API).
  const fieldDrafts: Record<string, FieldDraft> = {};
  const updateFieldDraft = useCallback((_key: string, _value: string) => {}, []);
  const clearFieldDraft = useCallback((_key: string) => {}, []);

  return {
    step,
    slots,
    flowError,
    report,
    extraction,
    entries,
    fieldDrafts,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    removeFile,
    updateEntry,
    deleteEntry,
    addEntry,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction,
    storeSupportingFiles,
    cancelExtraction,
    continueToValidate,
    reset,
    processingStage,
    isBusy,
  };
}
