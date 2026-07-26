/**
 * Bounded free-text helpers — not for person names or structured identifiers.
 */

export const FREE_TEXT_MAX_LENGTH = {
  /** Chat composer / short messages */
  chatMessage: 4000,
  /** Search boxes */
  searchQuery: 200,
  /** Employee number / department-style identifiers */
  identifier: 64,
  /** Single-line notes, reasons, KV labels */
  shortNote: 500,
  /** Multiline notes / rule drafts (align with digital-form ceiling) */
  longNote: 8000,
  /** Passwords — length cap only; never mutate spaces */
  password: 128,
} as const;

/** Remove C0 control chars except tab/newline/carriage-return when multiline. */
export function stripControlChars(raw: string, options: { allowNewlines?: boolean } = {}): string {
  const allowNewlines = options.allowNewlines ?? false;
  return (raw || '').replace(allowNewlines ? /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g : /[\u0000-\u001F\u007F]/g, '');
}

/** Trim edges; optionally collapse internal runs of spaces (single-line fields). */
export function normalizeFreeText(
  raw: string,
  options: { collapseWhitespace?: boolean; allowNewlines?: boolean; maxLength?: number } = {},
): string {
  let value = stripControlChars(raw, { allowNewlines: options.allowNewlines });
  if (options.collapseWhitespace && !options.allowNewlines) {
    value = value.replace(/[ \t\f\v]+/g, ' ').trim();
  } else {
    value = value.trim();
  }
  if (options.maxLength != null && value.length > options.maxLength) {
    value = value.slice(0, options.maxLength);
  }
  return value;
}

/** Soft clamp while typing — does not trim mid-edit trailing spaces. */
export function clampFreeTextInput(
  raw: string,
  maxLength: number,
  options: { allowNewlines?: boolean } = {},
): string {
  const cleaned = stripControlChars(raw, { allowNewlines: options.allowNewlines });
  return cleaned.length > maxLength ? cleaned.slice(0, maxLength) : cleaned;
}
