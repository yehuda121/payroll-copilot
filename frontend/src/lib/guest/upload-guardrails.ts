import type { TFunction } from 'i18next';

export type UploadGuardrailResult =
  | { ok: true }
  | { ok: false; message: string };

const MAX_UPLOAD_MB = 50;

const SLOT_ACCEPT: Record<string, string[]> = {
  payslip: ['application/pdf', 'image/png', 'image/jpeg'],
  attendance: [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
  ],
  contract: ['application/pdf'],
  national_id: ['application/pdf', 'image/png', 'image/jpeg'],
  bank_details: ['application/pdf', 'image/png', 'image/jpeg'],
  tax_form: ['application/pdf', 'image/png', 'image/jpeg'],
};

const INJECTION_PATTERNS = [
  'ignore previous instructions',
  'ignore all previous instructions',
  'system prompt',
  'jailbreak',
];

export async function validateUploadFile(
  slotId: string,
  file: File,
  existingNames: string[],
  t: TFunction,
): Promise<UploadGuardrailResult> {
  if (!file || file.size === 0) {
    return { ok: false, message: t('uploadErrors.empty') };
  }

  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return { ok: false, message: t('uploadErrors.tooLarge', { max: MAX_UPLOAD_MB }) };
  }

  if (existingNames.includes(file.name)) {
    return { ok: false, message: t('uploadErrors.duplicate') };
  }

  const allowed = SLOT_ACCEPT[slotId];
  if (allowed && file.type && !allowed.includes(file.type)) {
    return {
      ok: false,
      message: t('uploadErrors.unsupportedType', { type: file.type || 'unknown' }),
    };
  }

  if (file.type === 'application/pdf') {
    const header = await file.slice(0, 4).text();
    if (!header.startsWith('%PDF')) {
      return { ok: false, message: t('uploadErrors.invalidPdf') };
    }
    const preview = await file.slice(0, 4096).arrayBuffer();
    const text = new TextDecoder().decode(preview);
    if (text.includes('/Encrypt')) {
      return { ok: false, message: t('uploadErrors.encryptedPdf') };
    }
  }

  if (file.type === 'text/csv' || file.name.toLowerCase().endsWith('.csv')) {
    const sample = await file.slice(0, 8000).text();
    const lowered = sample.toLowerCase();
    if (INJECTION_PATTERNS.some((pattern) => lowered.includes(pattern))) {
      return {
        ok: false,
        message: t('uploadErrors.injection'),
      };
    }
  }

  return { ok: true };
}
