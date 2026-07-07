import { useCallback, useMemo, useState } from 'react';
import { GUEST_DOCUMENT_SLOTS, type GuestDocumentSlotId } from '../lib/guest/document-slots';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import { adaptValidationReport } from '../lib/guest/validation-report-adapter';
import { authService } from '../services/auth';
import { documentsService } from '../services/documents';
import { validationService } from '../services/validation';
import type { GuestValidationReport } from '../types/validation-report';

export type UploadSlotState = {
  file: File;
  documentId?: string;
  error?: string;
};

export type ValidationFlowStep = 'upload' | 'validating' | 'report';

export function useGuestValidationFlow() {
  const [step, setStep] = useState<ValidationFlowStep>('upload');
  const [slots, setSlots] = useState<Partial<Record<GuestDocumentSlotId, UploadSlotState>>>({});
  const [flowError, setFlowError] = useState<string | null>(null);
  const [report, setReport] = useState<GuestValidationReport | null>(null);

  const selectedNames = useMemo(
    () => Object.values(slots).map((slot) => slot?.file.name).filter(Boolean) as string[],
    [slots],
  );

  const selectFile = useCallback(
    async (slotId: GuestDocumentSlotId, file: File) => {
      const result = await validateUploadFile(slotId, file, selectedNames);
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
    [selectedNames],
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
      setFlowError('A payslip is required before validation can run.');
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
        const response = await documentsService.upload(selected.file, slot.backendType);
        uploadedIds[slot.id] = response.document_id;
        setSlots((prev) => ({
          ...prev,
          [slot.id]: { ...selected, documentId: response.document_id },
        }));
      }

      const payslipId = uploadedIds.payslip;
      if (!payslipId) {
        throw new Error('Payslip upload did not complete.');
      }

      const supportingIds = GUEST_DOCUMENT_SLOTS.filter(
        (slot) => slot.id !== 'payslip' && uploadedIds[slot.id],
      ).map((slot) => uploadedIds[slot.id] as string);

      const validation = await validationService.runValidation({
        document_id: payslipId,
        supporting_document_ids: supportingIds,
      });

      setReport(adaptValidationReport(validation));
      setStep('report');
    } catch (err) {
      setFlowError(err instanceof Error ? err.message : 'Validation could not be completed.');
      setStep('upload');
    }
  }, [slots]);

  const reset = useCallback(() => {
    setSlots({});
    setReport(null);
    setFlowError(null);
    setStep('upload');
  }, []);

  return {
    step,
    slots,
    flowError,
    report,
    selectFile,
    removeFile,
    runValidation,
    reset,
  };
}
