/**
 * Israeli National ID checksum — port of backend
 * `payroll_copilot.application.services.employee_fixed_document_extractor.is_valid_israeli_id`.
 * Keep algorithm identical; do not invent a second checksum.
 */

export function normalizeNationalIdDigits(raw: string): string {
  return (raw || '').replace(/\D/g, '');
}

export type NationalIdValidationResult =
  | { ok: true; digits: string }
  | { ok: false; code: 'empty' | 'digits_only' | 'length' | 'checksum' };

/**
 * Validate Israeli ID for manual entry.
 * Requires digits-only input of exactly 9 digits plus checksum.
 */
export function validateNationalId(raw: string): NationalIdValidationResult {
  const trimmed = (raw || '').trim();
  if (!trimmed) return { ok: false, code: 'empty' };
  if (/\D/.test(trimmed)) return { ok: false, code: 'digits_only' };
  const digits = normalizeNationalIdDigits(trimmed);
  if (digits.length !== 9) return { ok: false, code: 'length' };
  if (!isValidIsraeliIdChecksum(digits)) return { ok: false, code: 'checksum' };
  return { ok: true, digits };
}

/** Same checksum as backend `is_valid_israeli_id` (after digit normalization). */
export function isValidIsraeliIdChecksum(raw: string): boolean {
  let digits = normalizeNationalIdDigits(raw);
  if (!digits || digits.length > 9) return false;
  digits = digits.padStart(9, '0');
  if (digits === '000000000') return false;
  let total = 0;
  for (let index = 0; index < digits.length; index += 1) {
    const product = Number(digits[index]) * (index % 2 === 0 ? 1 : 2);
    total += product < 10 ? product : product - 9;
  }
  return total % 10 === 0;
}
