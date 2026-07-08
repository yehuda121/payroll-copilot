import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GUEST_DOCUMENT_SLOTS, type GuestDocumentSlotId } from '../lib/guest/document-slots';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import { adaptValidationReport } from '../lib/guest/validation-report-adapter';
import { useAppLocale } from './useAppLocale';
import { authService } from '../services/auth';
import { documentsService } from '../services/documents';
import { validationService } from '../services/validation';
import type { DocumentLanguage } from '../types/api';
import type { GuestValidationReport } from '../types/validation-report';

export type UploadSlotState = {
  file: File;
  documentId?: string;
  error?: string;
};

export type ValidationFlowStep = 'upload' | 'validating' | 'report';

export function useGuestValidationFlow() {
  const { t } = useTranslation();
  const { locale } = useAppLocale();
  const [step, setStep] = useState<ValidationFlowStep>('upload');
  const [slots, setSlots] = useState<Partial<Record<GuestDocumentSlotId, UploadSlotState>>>({});
  const [flowError, setFlowError] = useState<string | null>(null);
  const [report, setReport] = useState<GuestValidationReport | null>(null);
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

  const runValidation = useCallback(async () => {
    const payslip = slots.payslip?.file;
    if (!payslip) {
      setFlowError(t('validate.payslipRequired'));
      return;
    }

    setFlowError(null);
    setStep('validating');

    try {
      await authService.createGuestSession();

      const uploadedIds: Partial<Record<GuestDocumentSlotId, string>> = {};
      for (const slot of GUEST_DOCUMENT_SLOTS) {
        const selected = slots[slot.id];
        if (!selected?.file || selected.error) {
          continue;
        }
        const response = await documentsService.upload(
          selected.file,
          slot.backendType,
          documentLanguage,
        );
        uploadedIds[slot.id] = response.document_id;
        setSlots((prev) => ({
          ...prev,
          [slot.id]: { ...selected, documentId: response.document_id },
        }));
      }

      const payslipId = uploadedIds.payslip;
      if (!payslipId) {
        throw new Error(t('validate.payslipUploadFailed'));
      }

      const supportingIds = GUEST_DOCUMENT_SLOTS.filter(
        (slot) => slot.id !== 'payslip' && uploadedIds[slot.id],
      ).map((slot) => uploadedIds[slot.id] as string);

      const validation = await validationService.runValidation({
        document_id: payslipId,
        supporting_document_ids: supportingIds,
        locale,
      });

      setReport(adaptValidationReport(validation, t));
      setStep('report');
    } catch (err) {
      setFlowError(err instanceof Error ? err.message : t('validate.validationFailed'));
      setStep('upload');
    }
  }, [slots, documentLanguage, locale, t]);

  const reset = useCallback(() => {
    setSlots({});
    setReport(null);
    setFlowError(null);
    setStep('upload');
    setDocumentLanguage('auto');
  }, []);

  return {
    step,
    slots,
    flowError,
    report,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    removeFile,
    runValidation,
    reset,
  };
}
