import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GUEST_DOCUMENT_SLOTS, type GuestDocumentSlotId } from '../lib/guest/document-slots';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import { adaptValidationReport } from '../lib/guest/validation-report-adapter';
import { useAppLocale } from './useAppLocale';
import { authService } from '../services/auth';
import { documentsService } from '../services/documents';
import { extractionService } from '../services/extraction';
import { validationService } from '../services/validation';
import type { DocumentLanguage, ExtractedPayslipField, GuestPayslipExtractionResponse } from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';

export type UploadSlotState = {
  file: File;
  documentId?: string;
  error?: string;
};

export type ValidationFlowStep = 'upload' | 'prepare' | 'review' | 'validating' | 'report';

export type FieldDraft = {
  value: string;
  clear: boolean;
  dirty: boolean;
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

export function useGuestValidationFlow() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [step, setStep] = useState<ValidationFlowStep>('upload');
  const [slots, setSlots] = useState<Partial<Record<GuestDocumentSlotId, UploadSlotState>>>({});
  const [flowError, setFlowError] = useState<string | null>(null);
  const [report, setReport] = useState<GuestValidationReport | null>(null);
  const [extraction, setExtraction] = useState<GuestPayslipExtractionResponse | null>(null);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('auto');

  const selectedNames = useMemo(
    () => Object.values(slots).map((slot) => slot?.file.name).filter(Boolean) as string[],
    [slots],
  );

  const selectFile = useCallback(
    async (slotId: GuestDocumentSlotId, file: File) => {
      const result = await validateUploadFile(slotId, file, selectedNames, t);
      if (!result.ok) {
        setSlots((prev) => ({
          ...prev,
          [slotId]: { file, error: result.message },
        }));
        return;
      }
      setSlots((prev) => ({ ...prev, [slotId]: { file } }));
      setFlowError(null);
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

  /** Extract → Review (no validation yet). */
  const startExtraction = useCallback(async () => {
    const payslip = slots.payslip?.file;
    if (!payslip) {
      setFlowError(t('validate.payslipRequired'));
      return;
    }

    setFlowError(null);
    setExtraction(null);
    setReport(null);
    setFieldDrafts({});
    setStep('prepare');

    try {
      await authService.createGuestSession();

      const extractionResponse = await extractionService.extractGuestPayslip(
        payslip,
        documentLanguage,
      );
      setExtraction(extractionResponse);
      initDrafts(extractionResponse.fields);
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
        return;
      }

      if (extractionResponse.parser_status === 'failed') {
        setFlowError(extractionResponse.error_message || t('validate.extractionParserFailed'));
        if (extractionResponse.fields.length === 0) {
          setStep('upload');
          return;
        }
      }

      for (const slot of GUEST_DOCUMENT_SLOTS.filter((item) => item.id !== 'payslip')) {
        const selected = slots[slot.id];
        if (!selected?.file || selected.error) {
          continue;
        }
        const response = await documentsService.upload(
          selected.file,
          slot.backendType,
          documentLanguage,
        );
        setSlots((prev) => ({
          ...prev,
          [slot.id]: { ...selected, documentId: response.document_id },
        }));
      }

      setStep('review');
    } catch (err) {
      setFlowError(err instanceof Error ? err.message : t('validate.extractionFailed'));
      setStep('upload');
    }
  }, [slots, documentLanguage, initDrafts, t]);

  /** Persist edits (if any) → Validate → Results. */
  const continueToValidate = useCallback(async () => {
    const documentId = slots.payslip?.documentId || extraction?.document_id;
    if (!documentId) {
      setFlowError(t('validate.extractionFailed'));
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

      let latestExtraction = extraction;
      if (corrections.length > 0) {
        latestExtraction = await extractionService.correctGuestExtraction(documentId, corrections);
        setExtraction(latestExtraction);
        initDrafts(latestExtraction.fields);
      }

      const supportingIds = GUEST_DOCUMENT_SLOTS.filter(
        (slot) => slot.id !== 'payslip' && slots[slot.id]?.documentId,
      ).map((slot) => slots[slot.id]!.documentId as string);

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
  }, [slots, extraction, fieldDrafts, locale, initDrafts, t]);

  const reset = useCallback(() => {
    setSlots({});
    setReport(null);
    setExtraction(null);
    setFieldDrafts({});
    setFlowError(null);
    setStep('upload');
    setDocumentLanguage('auto');
  }, []);

  return {
    step,
    slots,
    flowError,
    report,
    extraction,
    fieldDrafts,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    removeFile,
    updateFieldDraft,
    clearFieldDraft,
    startExtraction,
    continueToValidate,
    reset,
  };
}
