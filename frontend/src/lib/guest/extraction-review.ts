import type { TFunction } from 'i18next';
import type {
  DynamicDocumentEntry,
  ExtractedPayslipField,
  GuestPayslipExtractionResponse,
} from '../../types/api';
import { isCanonicalPayrollFieldKey } from './payroll-field-keys';

export type ExtractionField = {
  key: string;
  label: string;
  displayValue: string;
  rawValue: unknown;
  status: string;
  confidenceLabel: string | null;
  sourceText: string | null;
  editedByUser: boolean;
  sectionId: string;
};

function hasNonEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  return String(value).trim() !== '';
}

/** Entry is showable when it came from the document (has a label and/or a value). */
export function isDocumentOriginEntry(entry: DynamicDocumentEntry): boolean {
  const hasKey = Boolean(entry.key?.trim());
  if (!hasKey && !hasNonEmptyValue(entry.value)) return false;
  // Drop empty snake_case schema placeholders the model may invent.
  if (!hasNonEmptyValue(entry.value) && isCanonicalPayrollFieldKey(entry.key || '')) {
    return false;
  }
  return true;
}

/**
 * Review list usability: at least one extracted/edited value exists.
 * Empty-value rows (label found, value missing) are shown but do not alone enable confirm.
 */
export function hasUsableDynamicEntries(entries: DynamicDocumentEntry[] | null | undefined): boolean {
  if (!entries || entries.length === 0) return false;
  return entries.some((entry) => hasNonEmptyValue(entry.value));
}

/**
 * Localized key for the review UI.
 * - Canonical identifiers → t("payroll.fields.<key>")
 * - Empty / unknown label → t("payroll.fields.unknown")
 * - User or document custom labels → shown exactly as stored
 */
export function getDynamicEntryDisplayKey(key: string, t: TFunction): string {
  const trimmed = key.trim();
  if (!trimmed) {
    return t('payroll.fields.unknown');
  }
  if (isCanonicalPayrollFieldKey(trimmed)) {
    return t(`payroll.fields.${trimmed}`);
  }
  return key;
}

export function serializeEntryValue(value: unknown): string {
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

export function parseEntryValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

export function createBlankEntry(): DynamicDocumentEntry {
  return {
    id: crypto.randomUUID(),
    key: '',
    value: '',
    confidence: null,
    page: null,
    source: 'user',
    source_text: null,
    section: null,
    kind: 'field',
    table_id: null,
    row_index: null,
    column: null,
  };
}

/** Group document-model entries by section title (order preserved). */
export function groupEntriesBySection(
  entries: DynamicDocumentEntry[],
): Array<{ section: string | null; entries: DynamicDocumentEntry[] }> {
  const groups: Array<{ section: string | null; entries: DynamicDocumentEntry[] }> = [];
  const indexBySection = new Map<string, number>();

  for (const entry of entries) {
    const section = entry.section?.trim() || null;
    const mapKey = section ?? '';
    const existing = indexBySection.get(mapKey);
    if (existing === undefined) {
      indexBySection.set(mapKey, groups.length);
      groups.push({ section, entries: [entry] });
    } else {
      groups[existing]?.entries.push(entry);
    }
  }
  return groups;
}

/**
 * Build review entries from the extraction API.
 * Prefer `entries` (document-first). Never synthesize empty canonical schema rows.
 */
export function entriesFromExtractionResponse(
  response: GuestPayslipExtractionResponse,
): DynamicDocumentEntry[] {
  if (Array.isArray(response.entries)) {
    return response.entries.filter(isDocumentOriginEntry).map((entry) => ({
      ...entry,
      key: entry.key?.trim() ?? '',
    }));
  }

  // Legacy/compat only: map schema fields that actually have document signal.
  // Never include MISSING empty placeholders from the full payroll schema.
  return (response.fields || [])
    .filter((field) => {
      const status = (field.status || '').toUpperCase();
      if (status !== 'FOUND' && status !== 'UNCERTAIN') return false;
      return hasNonEmptyValue(field.value) || Boolean(field.key?.trim());
    })
    .map((field) => ({
      id: crypto.randomUUID(),
      key: field.key?.trim() ?? '',
      value: field.value,
      confidence: field.confidence ?? null,
      page: null,
      source: 'ocr',
      source_text: field.source_text ?? null,
    }));
}

/** Legacy helper kept for employee/validation wizard imports. */
export function isImageFile(file: File | undefined): boolean {
  if (!file) return false;
  const name = file.name.toLowerCase();
  return (
    file.type.startsWith('image/') ||
    name.endsWith('.png') ||
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg')
  );
}

/** @deprecated Prefer hasUsableDynamicEntries for landing. */
export function hasUsableExtractedFields(
  fields: Array<Partial<ExtractedPayslipField>> | null | undefined,
): boolean {
  if (!fields || fields.length === 0) return false;
  return fields.some((field) => {
    const status = (field.status || '').toUpperCase();
    if (status !== 'FOUND' && status !== 'UNCERTAIN') return false;
    return field.value !== null && field.value !== undefined && String(field.value).trim() !== '';
  });
}

/**
 * Schema-era review helper for Employee Portal (fixed PAYSLIP fields).
 * Landing page uses dynamic entries instead.
 */
export function buildExtractionReviewFields(
  fields: ExtractedPayslipField[] | undefined,
  t: TFunction,
): ExtractionField[] {
  return (fields || []).map((field) => {
    let status = field.status || 'MISSING';
    if (
      status === 'UNCERTAIN' &&
      (field.value === null || field.value === undefined || field.value === '')
    ) {
      status = 'MISSING';
    }
    return {
      key: field.key,
      label: isCanonicalPayrollFieldKey(field.key)
        ? t(`payroll.fields.${field.key}`)
        : t(`validate.field.${field.key}`, { defaultValue: field.key }),
      displayValue: serializeEntryValue(field.value),
      rawValue: field.value ?? null,
      status,
      confidenceLabel:
        field.confidence == null || Number.isNaN(field.confidence)
          ? null
          : `${Math.round(field.confidence * 100)}%`,
      sourceText: field.source_text ?? null,
      editedByUser: Boolean(field.edited_by_user),
      sectionId: 'basics',
    };
  });
}

export function groupFieldsBySection(
  fields: ExtractionField[],
): Array<{ section: { id: string; titleKey: string; fieldKeys: string[] }; fields: ExtractionField[] }> {
  if (fields.length === 0) return [];
  return [
    {
      section: {
        id: 'basics',
        titleKey: 'landingChat.form.sections.basics',
        fieldKeys: fields.map((f) => f.key),
      },
      fields,
    },
  ];
}
