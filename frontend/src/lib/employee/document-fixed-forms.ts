import type { PersistentDocumentType } from '../../hooks/useEmployeeDocumentWorkspace';

export const ID_CARD_FIELD_KEYS = [
  'full_name',
  'national_id',
  'birth_date',
] as const;

/** Canonical appendix field — value is AppendixChild[]. Count is derived from length. */
export const ID_APPENDIX_CHILDREN_KEY = 'children' as const;

export type FixedDocumentFieldKey = (typeof ID_CARD_FIELD_KEYS)[number];

export type AppendixChild = {
  name: string;
  birth_date: string;
};

export function fixedFieldKeysFor(
  documentType: PersistentDocumentType,
): readonly FixedDocumentFieldKey[] | null {
  if (documentType === 'national_id') return ID_CARD_FIELD_KEYS;
  return null;
}

export function isAppendixDocumentType(documentType: PersistentDocumentType): boolean {
  return documentType === 'id_appendix';
}

export function emptyFixedFieldValues(
  documentType: PersistentDocumentType,
): Record<string, string> {
  const keys = fixedFieldKeysFor(documentType);
  if (!keys) return {};
  return Object.fromEntries(keys.map((key) => [key, '']));
}

export function emptyAppendixChildren(): AppendixChild[] {
  return [];
}

export function parseAppendixChildren(value: unknown): AppendixChild[] {
  let raw = value;
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    try {
      raw = JSON.parse(trimmed) as unknown;
    } catch {
      return [];
    }
  }
  if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'children' in raw) {
    raw = (raw as { children: unknown }).children;
  }
  if (!Array.isArray(raw)) return [];
  const children: AppendixChild[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const nameRaw = row.name ?? row.child_name;
    const birthRaw = row.birth_date ?? row.date_of_birth;
    const name = nameRaw == null ? '' : String(nameRaw).trim();
    const birth_date = birthRaw == null ? '' : String(birthRaw).trim();
    if (!name && !birth_date) continue;
    children.push({ name, birth_date });
  }
  return children;
}

export function formatAppendixChildPreview(child: AppendixChild, emptyLabel: string): string {
  const parts = [child.name, child.birth_date].filter((part) => part.trim());
  return parts.length ? parts.join(' · ') : emptyLabel;
}
