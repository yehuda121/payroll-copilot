/**
 * Birth-date parse / normalize for Document Center forms.
 * Canonical storage format: YYYY-MM-DD (HTML date input + ISO date).
 */

export type BirthDateParseResult =
  | { ok: true; iso: string }
  | { ok: false; code: 'empty' | 'invalid' };

function isValidYmd(year: number, month: number, day: number): boolean {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return false;
  if (year < 1900 || year > 2100) return false;
  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

function toIso(year: number, month: number, day: number): string | null {
  if (!isValidYmd(year, month, day)) return null;
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * Parse common user / OCR birth-date formats into YYYY-MM-DD.
 * Supports: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, YYYY.MM.DD.
 */
export function parseBirthDate(raw: string): BirthDateParseResult {
  const trimmed = (raw || '').trim();
  if (!trimmed) return { ok: false, code: 'empty' };

  const isoMatch = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(trimmed);
  if (isoMatch) {
    const iso = toIso(Number(isoMatch[1]), Number(isoMatch[2]), Number(isoMatch[3]));
    return iso ? { ok: true, iso } : { ok: false, code: 'invalid' };
  }

  const dmyMatch = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/.exec(trimmed);
  if (dmyMatch) {
    const iso = toIso(Number(dmyMatch[3]), Number(dmyMatch[2]), Number(dmyMatch[1]));
    return iso ? { ok: true, iso } : { ok: false, code: 'invalid' };
  }

  return { ok: false, code: 'invalid' };
}

/** Normalize to YYYY-MM-DD when valid; otherwise return original trimmed string. */
export function normalizeBirthDateInput(raw: string): string {
  const parsed = parseBirthDate(raw);
  if (parsed.ok) return parsed.iso;
  return (raw || '').trim();
}

/** Value for `<input type="date">` — empty when unparseable. */
export function birthDateToDateInputValue(raw: string): string {
  const parsed = parseBirthDate(raw);
  return parsed.ok ? parsed.iso : '';
}
