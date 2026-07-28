/**
 * Presentation metadata for employee fixed-document fields.
 * Mirrors the Digital Payslip field-registry pattern: labels come only from
 * registered i18n keys — never from string manipulation of canonical keys.
 *
 * Does not change extraction, persistence, schemas, or APIs.
 */

import type { TFunction } from 'i18next';
import type { PersistentDocumentType } from '../../hooks/useEmployeeDocumentWorkspace';
import {
  CONTRACT_FIELD_KEYS,
  ID_APPENDIX_CHILDREN_KEY,
  ID_CARD_FIELD_KEYS,
} from './document-fixed-forms';

export type DocumentFieldSection =
  | 'identity'
  | 'family'
  | 'employment'
  | 'compensation';

export type DocumentFieldDefinition = {
  canonical_key: string;
  document_type: PersistentDocumentType;
  label_i18n_key: string;
  description_i18n_key?: string;
  section: DocumentFieldSection;
  display_order: number;
};

type DefInput = {
  key: string;
  document_type: PersistentDocumentType;
  section: DocumentFieldSection;
  order: number;
  description_i18n_key?: string;
};

const SECTION_ORDER: DocumentFieldSection[] = [
  'identity',
  'family',
  'employment',
  'compensation',
];

const DEFINITIONS: DefInput[] = [
  // Identity Card
  { key: 'full_name', document_type: 'national_id', section: 'identity', order: 10 },
  { key: 'national_id', document_type: 'national_id', section: 'identity', order: 20 },
  { key: 'birth_date', document_type: 'national_id', section: 'identity', order: 30 },

  // ID Appendix (collection + nested child row fields)
  { key: ID_APPENDIX_CHILDREN_KEY, document_type: 'id_appendix', section: 'family', order: 10 },
  { key: 'child_name', document_type: 'id_appendix', section: 'family', order: 20 },
  { key: 'child_birth_date', document_type: 'id_appendix', section: 'family', order: 30 },

  // Employment Contract — Employment
  {
    key: 'employment_commencement_date',
    document_type: 'contract',
    section: 'employment',
    order: 10,
  },
  { key: 'salary_basis', document_type: 'contract', section: 'employment', order: 20 },
  { key: 'effective_from', document_type: 'contract', section: 'employment', order: 30 },
  { key: 'effective_to', document_type: 'contract', section: 'employment', order: 40 },

  // Employment Contract — Compensation
  {
    key: 'contractual_monthly_salary',
    document_type: 'contract',
    section: 'compensation',
    order: 50,
  },
  {
    key: 'contractual_hourly_rate',
    document_type: 'contract',
    section: 'compensation',
    order: 60,
  },
  {
    key: 'contractual_daily_rate',
    document_type: 'contract',
    section: 'compensation',
    order: 70,
  },
];

function buildDefinition(input: DefInput): DocumentFieldDefinition {
  return {
    canonical_key: input.key,
    document_type: input.document_type,
    label_i18n_key: `employee.documents.fields.${input.key}`,
    description_i18n_key: input.description_i18n_key,
    section: input.section,
    display_order: input.order,
  };
}

function registryKey(documentType: PersistentDocumentType, canonicalKey: string): string {
  return `${documentType}::${canonicalKey}`;
}

function buildRegistry(): Record<string, DocumentFieldDefinition> {
  const defs: Record<string, DocumentFieldDefinition> = {};
  for (const item of DEFINITIONS) {
    defs[registryKey(item.document_type, item.key)] = buildDefinition(item);
  }
  return defs;
}

export const DOCUMENT_FIELD_REGISTRY = buildRegistry();

export function sectionTitleI18nKey(section: DocumentFieldSection): string {
  return `employee.documents.fieldSections.${section}`;
}

export function getDocumentFieldDefinition(
  documentType: PersistentDocumentType,
  canonicalKey: string,
): DocumentFieldDefinition | null {
  const key = canonicalKey.trim();
  if (!key) return null;
  return DOCUMENT_FIELD_REGISTRY[registryKey(documentType, key)] ?? null;
}

/**
 * Resolve a business label from the registry only.
 * Missing registry entries return null — callers must not invent labels.
 */
export function resolveDocumentFieldLabel(
  documentType: PersistentDocumentType,
  canonicalKey: string,
  t: TFunction,
): string | null {
  const def = getDocumentFieldDefinition(documentType, canonicalKey);
  if (!def) return null;
  return t(def.label_i18n_key);
}

export function resolveDocumentFieldSectionTitle(
  section: DocumentFieldSection,
  t: TFunction,
): string {
  return t(sectionTitleI18nKey(section));
}

export function orderedDocumentFieldDefinitions(
  documentType: PersistentDocumentType,
): DocumentFieldDefinition[] {
  return Object.values(DOCUMENT_FIELD_REGISTRY)
    .filter((def) => def.document_type === documentType)
    .sort((a, b) => a.display_order - b.display_order || a.canonical_key.localeCompare(b.canonical_key));
}

/** Scalar / form keys for a document type (excludes nested appendix child_* helpers). */
export function orderedFormFieldKeys(
  documentType: PersistentDocumentType,
): string[] {
  if (documentType === 'national_id') {
    return orderedDocumentFieldDefinitions(documentType)
      .map((def) => def.canonical_key)
      .filter((key) => (ID_CARD_FIELD_KEYS as readonly string[]).includes(key));
  }
  if (documentType === 'contract') {
    return orderedDocumentFieldDefinitions(documentType)
      .map((def) => def.canonical_key)
      .filter((key) => (CONTRACT_FIELD_KEYS as readonly string[]).includes(key));
  }
  return [];
}

export type DocumentFieldPreviewSection = {
  id: DocumentFieldSection;
  titleKey: string;
  fields: DocumentFieldDefinition[];
};

export function documentFieldSectionsForType(
  documentType: PersistentDocumentType,
  fieldKeys?: readonly string[],
): DocumentFieldPreviewSection[] {
  const allowed = fieldKeys ? new Set(fieldKeys) : null;
  const defs = orderedDocumentFieldDefinitions(documentType).filter((def) => {
    if (allowed && !allowed.has(def.canonical_key)) return false;
    // Nested appendix helpers are not top-level preview fields.
    if (documentType === 'id_appendix' && def.canonical_key !== ID_APPENDIX_CHILDREN_KEY) {
      return false;
    }
    return true;
  });

  const bySection = new Map<DocumentFieldSection, DocumentFieldDefinition[]>();
  for (const def of defs) {
    const list = bySection.get(def.section) ?? [];
    list.push(def);
    bySection.set(def.section, list);
  }

  return SECTION_ORDER.filter((section) => bySection.has(section)).map((section) => ({
    id: section,
    titleKey: sectionTitleI18nKey(section),
    fields: bySection.get(section)!,
  }));
}

/** Assert registry covers every known fixed-form key (tests / sync checks). */
export function documentFieldRegistryCoverage(): {
  missing: string[];
  extraFormKeys: string[];
} {
  const missing: string[] = [];
  for (const key of ID_CARD_FIELD_KEYS) {
    if (!getDocumentFieldDefinition('national_id', key)) {
      missing.push(`national_id.${key}`);
    }
  }
  for (const key of CONTRACT_FIELD_KEYS) {
    if (!getDocumentFieldDefinition('contract', key)) {
      missing.push(`contract.${key}`);
    }
  }
  if (!getDocumentFieldDefinition('id_appendix', ID_APPENDIX_CHILDREN_KEY)) {
    missing.push(`id_appendix.${ID_APPENDIX_CHILDREN_KEY}`);
  }
  for (const nested of ['child_name', 'child_birth_date'] as const) {
    if (!getDocumentFieldDefinition('id_appendix', nested)) {
      missing.push(`id_appendix.${nested}`);
    }
  }

  const knownForm = new Set<string>([
    ...ID_CARD_FIELD_KEYS.map((k) => registryKey('national_id', k)),
    ...CONTRACT_FIELD_KEYS.map((k) => registryKey('contract', k)),
    registryKey('id_appendix', ID_APPENDIX_CHILDREN_KEY),
    registryKey('id_appendix', 'child_name'),
    registryKey('id_appendix', 'child_birth_date'),
  ]);
  const extraFormKeys = Object.keys(DOCUMENT_FIELD_REGISTRY).filter((k) => !knownForm.has(k));

  return { missing, extraFormKeys };
}
