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
): Promise<UploadGuardrailResult> {
  if (!file || file.size === 0) {
    return { ok: false, message: 'The selected file is empty.' };
  }

  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return { ok: false, message: `File exceeds the ${MAX_UPLOAD_MB}MB upload limit.` };
  }

  if (existingNames.includes(file.name)) {
    return { ok: false, message: 'This file has already been selected for upload.' };
  }

  const allowed = SLOT_ACCEPT[slotId];
  if (allowed && file.type && !allowed.includes(file.type)) {
    return {
      ok: false,
      message: `Unsupported file type for this document slot (${file.type || 'unknown'}).`,
    };
  }

  if (file.type === 'application/pdf') {
    const header = await file.slice(0, 4).text();
    if (!header.startsWith('%PDF')) {
      return { ok: false, message: 'The PDF file appears to be corrupted or invalid.' };
    }
    const preview = await file.slice(0, 4096).arrayBuffer();
    const text = new TextDecoder().decode(preview);
    if (text.includes('/Encrypt')) {
      return { ok: false, message: 'Password-protected PDF files are not supported.' };
    }
  }

  if (file.type === 'text/csv' || file.name.toLowerCase().endsWith('.csv')) {
    const sample = await file.slice(0, 8000).text();
    const lowered = sample.toLowerCase();
    if (INJECTION_PATTERNS.some((pattern) => lowered.includes(pattern))) {
      return {
        ok: false,
        message: 'The uploaded file contains unsupported instruction-like content.',
      };
    }
  }

  return { ok: true };
}
