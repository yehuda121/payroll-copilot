import type { PersistentDocumentType } from '../../hooks/useEmployeeDocumentWorkspace';

export const ID_CARD_FIELD_KEYS = [
  'full_name',
  'national_id',
  'birth_date',
] as const;

export const ID_APPENDIX_FIELD_KEYS = [
  'marital_status',
  'number_of_children',
  'residency_status',
  'citizenship',
] as const;

export type FixedDocumentFieldKey =
  | (typeof ID_CARD_FIELD_KEYS)[number]
  | (typeof ID_APPENDIX_FIELD_KEYS)[number];

export function fixedFieldKeysFor(
  documentType: PersistentDocumentType,
): readonly FixedDocumentFieldKey[] | null {
  if (documentType === 'national_id') return ID_CARD_FIELD_KEYS;
  if (documentType === 'id_appendix') return ID_APPENDIX_FIELD_KEYS;
  return null;
}

export function emptyFixedFieldValues(
  documentType: PersistentDocumentType,
): Record<string, string> {
  const keys = fixedFieldKeysFor(documentType);
  if (!keys) return {};
  return Object.fromEntries(keys.map((key) => [key, '']));
}
