/**
 * Filename / MIME-based guest document slot detection.
 * Uses token / phrase matching — never naive substring checks like includes("id").
 */

import type { GuestDocumentSlotId } from './document-slots';

/** Recognizable document kinds (slot catalog + adjacent kinds). */
export type DetectedDocumentKind =
  | 'payslip'
  | 'national_id'
  | 'attendance'
  | 'contract'
  | 'bank_details'
  | 'tax_form';

function normalizeFilename(name: string): string {
  return name
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\.[^.]+$/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Whole-token match (Unicode letters + digits). Avoids matching "id" inside "valid". */
function hasToken(haystack: string, token: string): boolean {
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?:^|[^\\p{L}\\p{N}])${escaped}(?:$|[^\\p{L}\\p{N}])`, 'u').test(haystack);
}

function hasAnyToken(haystack: string, tokens: string[]): boolean {
  return tokens.some((token) => hasToken(haystack, token));
}

function hasPhrase(haystack: string, phrase: string): boolean {
  return haystack.includes(phrase.toLowerCase());
}

const PAYSLIP_TOKENS = [
  'payslip',
  'salary',
  'wage',
  'payroll',
  'slip',
  'תלוש',
  'שכר',
  'משכורת',
  'قسيمة',
  'راتب',
];

const CONTRACT_TOKENS = ['contract', 'agreement', 'חוזה', 'הסכם', 'عقد', 'اتفاقية'];

const ATTENDANCE_TOKENS = [
  'attendance',
  'timesheet',
  'punch',
  'clock',
  'נוכחות',
  'حضور',
];

const NATIONAL_ID_TOKENS = [
  'teudat',
  'passport',
  'זהות',
  'תז',
  'هوية',
];

const BANK_TOKENS = ['bank', 'iban', 'routing', 'bankdetails', 'בנק', 'بنك'];

const TAX_TOKENS = ['taxform', 'withholding', 'irs', 'ضريبة'];

/**
 * Detect document kind from filename + MIME.
 * Payslip phrases win so names like payslip_valid.png / salary_2025.pdf / תלוש_שכר.pdf stay payslips.
 */
export function detectDocumentKindFromFile(file: {
  name: string;
  type?: string;
}): DetectedDocumentKind {
  const base = normalizeFilename(file.name || '');
  const mime = (file.type || '').toLowerCase();

  if (
    hasAnyToken(base, PAYSLIP_TOKENS) ||
    hasPhrase(base, 'pay slip') ||
    hasPhrase(base, 'תלוש שכר')
  ) {
    return 'payslip';
  }

  if (
    hasAnyToken(base, CONTRACT_TOKENS) ||
    hasPhrase(base, 'employment contract') ||
    hasPhrase(base, 'employment agreement')
  ) {
    return 'contract';
  }

  if (
    hasAnyToken(base, ATTENDANCE_TOKENS) ||
    hasPhrase(base, 'time sheet') ||
    hasPhrase(base, 'שעות עבודה')
  ) {
    return 'attendance';
  }

  if (
    hasAnyToken(base, NATIONAL_ID_TOKENS) ||
    hasPhrase(base, 'national id') ||
    hasPhrase(base, 'national_id') ||
    hasPhrase(base, 'id card') ||
    hasPhrase(base, 'identity card') ||
    hasPhrase(base, 'תעודת זהות') ||
    hasPhrase(base, 'teudat zehut') ||
    hasPhrase(base, 'بطاقة هوية')
  ) {
    return 'national_id';
  }

  if (
    hasAnyToken(base, BANK_TOKENS) ||
    hasPhrase(base, 'bank details') ||
    hasPhrase(base, 'account statement') ||
    hasPhrase(base, 'חשבון בנק')
  ) {
    return 'bank_details';
  }

  if (
    hasAnyToken(base, TAX_TOKENS) ||
    hasPhrase(base, 'tax form') ||
    hasPhrase(base, 'טופס 106') ||
    hasPhrase(base, 'טופס 101') ||
    hasPhrase(base, 'מס הכנסה')
  ) {
    return 'tax_form';
  }

  if (mime.includes('pdf') || mime.startsWith('image/')) {
    return 'payslip';
  }
  return 'payslip';
}

/**
 * Map to guest composer slot ids. Bank/tax map to dedicated disabled catalog slots.
 */
export function detectSlotFromFile(file: { name: string; type?: string }): GuestDocumentSlotId {
  const kind = detectDocumentKindFromFile(file);
  return kind;
}
