/**
 * Employee Digital Form field typing (UI only).
 * Does not change extraction or persistence.
 */

export type EmployeeFieldType =
  | 'text'
  | 'multiline_text'
  | 'number'
  | 'currency'
  | 'percentage'
  | 'date'
  | 'boolean'
  | 'table'
  | 'unknown';

const CURRENCY_KEYS = new Set([
  'base_salary',
  'gross_salary',
  'net_salary',
  'travel_expenses',
  'income_tax',
  'national_insurance',
  'health_tax',
  'pension_employee',
  'pension_employer',
  'severance',
  'training_fund',
  'total_deductions',
  'hourly_rate',
]);

const NUMBER_KEYS = new Set([
  'regular_hours',
  'overtime_hours',
  'vacation_balance',
  'sick_leave_balance',
]);

const PERCENTAGE_KEYS = new Set<string>([]);

const DATE_KEYS = new Set(['pay_period']);

const MULTILINE_KEYS = new Set(['messages', 'notes', 'comments', 'remarks']);

const BOOLEAN_KEYS = new Set<string>([]);

export const FIELD_VALUE_MAX_CHARS = 8000;
export const FIELD_PREVIEW_MAX_CHARS = 72;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function detectEmployeeFieldType(key: string, value: unknown): EmployeeFieldType {
  const normalizedKey = key.trim().toLowerCase();

  if (Array.isArray(value) || (isPlainObject(value) && ('rows' in value || 'columns' in value))) {
    return 'table';
  }
  if (CURRENCY_KEYS.has(normalizedKey)) return 'currency';
  if (PERCENTAGE_KEYS.has(normalizedKey)) return 'percentage';
  if (NUMBER_KEYS.has(normalizedKey)) return 'number';
  if (DATE_KEYS.has(normalizedKey)) return 'date';
  if (BOOLEAN_KEYS.has(normalizedKey)) return 'boolean';
  if (MULTILINE_KEYS.has(normalizedKey)) return 'multiline_text';

  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number' && Number.isFinite(value)) {
    return CURRENCY_KEYS.has(normalizedKey) ? 'currency' : 'number';
  }

  const text = value == null ? '' : String(value);
  if (text.includes('\n') || text.length > FIELD_PREVIEW_MAX_CHARS) {
    return 'multiline_text';
  }
  if (/^-?\d+(\.\d+)?%?$/.test(text.trim()) && text.trim().endsWith('%')) {
    return 'percentage';
  }
  if (/^-?\d+(\.\d+)?$/.test(text.trim()) && text.trim().length > 0) {
    return 'number';
  }
  if (/^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$/.test(text.trim()) || /^\d{1,2}\/\d{4}$/.test(text.trim())) {
    return 'date';
  }
  if (/^(true|false|yes|no)$/i.test(text.trim())) return 'boolean';

  if (text.trim()) return 'text';
  return 'unknown';
}

export function serializeFieldValue(value: unknown): string {
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

export function formatFieldPreview(
  value: string,
  type: EmployeeFieldType,
  locale: string,
): string {
  const trimmed = value.trim();
  if (!trimmed) return '';

  if (type === 'table') {
    return truncatePreview(trimmed);
  }

  if ((type === 'number' || type === 'currency' || type === 'percentage') && /^-?\d+(\.\d+)?%?$/.test(trimmed)) {
    const numeric = Number(trimmed.replace(/%$/, ''));
    if (Number.isFinite(numeric)) {
      try {
        if (type === 'currency') {
          return new Intl.NumberFormat(locale, {
            maximumFractionDigits: 2,
            minimumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
          }).format(numeric);
        }
        if (type === 'percentage') {
          return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(numeric)}%`;
        }
        return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(numeric);
      } catch {
        // fall through
      }
    }
  }

  if (type === 'multiline_text' || trimmed.length > FIELD_PREVIEW_MAX_CHARS || trimmed.includes('\n')) {
    return truncatePreview(trimmed.replace(/\s+/g, ' '));
  }

  return trimmed;
}

export function truncatePreview(value: string, max = FIELD_PREVIEW_MAX_CHARS): string {
  if (value.length <= max) return value;
  return `${value.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

export function fieldSpansColumns(type: EmployeeFieldType, value = ''): 1 | 2 {
  if (type === 'multiline_text' || type === 'table') return 2;
  // Long content (e.g. department, notes) spans two columns when the grid allows it.
  if (value.includes('\n') || value.trim().length > FIELD_PREVIEW_MAX_CHARS) return 2;
  return 1;
}

export type FieldNormalizeResult =
  | { ok: true; value: string }
  | { ok: false; messageKey: string };

/** UX-only client normalize before save. Backend remains source of truth. */
export function normalizeFieldInput(raw: string, type: EmployeeFieldType): FieldNormalizeResult {
  const value = raw.replace(/^\uFEFF/, '').trimEnd();
  const trimmed = value.trimStart();

  if (trimmed.length > FIELD_VALUE_MAX_CHARS) {
    return { ok: false, messageKey: 'employee.digitalForm.valueTooLong' };
  }

  if (type === 'number' || type === 'currency' || type === 'percentage') {
    if (!trimmed) return { ok: true, value: '' };
    const cleaned = trimmed.replace(/%$/, '').replace(/,/g, '');
    if (!/^-?\d+(\.\d+)?$/.test(cleaned)) {
      return { ok: false, messageKey: 'employee.digitalForm.invalidNumber' };
    }
    return { ok: true, value: type === 'percentage' && raw.trim().endsWith('%') ? `${cleaned}%` : cleaned };
  }

  if (type === 'boolean') {
    if (!trimmed) return { ok: true, value: '' };
    const lower = trimmed.toLowerCase();
    if (!['true', 'false', 'yes', 'no', '1', '0'].includes(lower)) {
      return { ok: false, messageKey: 'employee.digitalForm.invalidBoolean' };
    }
    return { ok: true, value: lower };
  }

  // Preserve intentional internal whitespace; only trim ends.
  return { ok: true, value: trimmed };
}

export function usesMultilineEditor(type: EmployeeFieldType): boolean {
  return type === 'multiline_text' || type === 'table';
}
