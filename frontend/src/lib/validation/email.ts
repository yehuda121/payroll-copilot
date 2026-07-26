/**
 * Format-only email helpers shared across accountant/employee/auth surfaces.
 * Not a mailbox existence check.
 */

export const EMAIL_MAX_LENGTH = 254;

export type EmailValidationResult =
  | { ok: true; value: string }
  | { ok: false; code: 'empty' | 'max_length' | 'format' };

/** Trim surrounding whitespace only — do not alter local-part casing for display. */
export function sanitizeEmailInput(raw: string): string {
  return (raw || '').trim();
}

/**
 * Structural local@domain.tld check.
 * Empty is invalid unless `allowEmpty` is true (optional overrides).
 */
export function validateEmailFormat(
  raw: string,
  options: { allowEmpty?: boolean } = {},
): EmailValidationResult {
  const value = sanitizeEmailInput(raw);
  if (!value) {
    return options.allowEmpty ? { ok: true, value: '' } : { ok: false, code: 'empty' };
  }
  if (value.length > EMAIL_MAX_LENGTH) return { ok: false, code: 'max_length' };
  // Same practical rule previously used by EmployeeForm / leave settings.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return { ok: false, code: 'format' };
  return { ok: true, value };
}

/** Boolean helper for optional fields (empty allowed). */
export function isValidEmailFormat(raw: string, allowEmpty = false): boolean {
  return validateEmailFormat(raw, { allowEmpty }).ok;
}
