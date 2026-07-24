/**
 * Field-type-aware text normalization and constraints for Document Center forms.
 */

export const FIELD_MAX_LENGTH = {
  personName: 120,
  nationalId: 9,
  birthDate: 32,
} as const;

export type PersonNameValidationResult =
  | { ok: true; value: string }
  | { ok: false; code: 'empty' | 'digits' | 'max_length' | 'invalid_chars' };

/** Collapse whitespace for human-readable text (names, labels). */
export function normalizeHumanText(raw: string): string {
  return (raw || '')
    .replace(/[\t\n\r\f\v]+/g, ' ')
    .replace(/ {2,}/g, ' ')
    .trim();
}

/**
 * Unicode-aware person name: letters + spaces/hyphens/apostrophes.
 * Rejects digits. Allows combining marks used by Hebrew/Arabic/Latin scripts.
 */
const PERSON_NAME_PATTERN =
  /^(?:[\p{L}\p{M}]+(?:['\u2019-][\p{L}\p{M}]+)*)(?:\s+(?:[\p{L}\p{M}]+(?:['\u2019-][\p{L}\p{M}]+)*))*$/u;

export function validatePersonName(raw: string): PersonNameValidationResult {
  const value = normalizeHumanText(raw);
  if (!value) return { ok: false, code: 'empty' };
  if (value.length > FIELD_MAX_LENGTH.personName) return { ok: false, code: 'max_length' };
  if (/\d/.test(value)) return { ok: false, code: 'digits' };
  if (!PERSON_NAME_PATTERN.test(value)) return { ok: false, code: 'invalid_chars' };
  return { ok: true, value };
}

export function normalizeFieldByKey(key: string, raw: unknown): unknown {
  if (typeof raw !== 'string') return raw;
  if (key === 'full_name' || key === 'child_name' || key === 'name') {
    return normalizeHumanText(raw);
  }
  if (key === 'national_id') {
    return raw.trim();
  }
  if (key === 'birth_date') {
    return raw.trim();
  }
  return raw;
}
