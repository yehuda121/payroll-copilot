import type { AppendixChild } from './document-fixed-forms';
import { parseBirthDate } from './birth-date';

export type AppendixChildRowError = {
  index: number;
  code: 'incomplete' | 'invalid_birth_date';
};

export type AppendixChildrenValidation =
  | { ok: true; children: AppendixChild[] }
  | { ok: false; errors: AppendixChildRowError[] };

/**
 * Empty rows (both blank) are dropped.
 * Rows with only one field filled are invalid.
 * Birth dates must parse when present.
 */
export function validateAppendixChildren(children: AppendixChild[]): AppendixChildrenValidation {
  const errors: AppendixChildRowError[] = [];
  const kept: AppendixChild[] = [];

  children.forEach((child, index) => {
    const name = (child.name || '').trim();
    const birthRaw = (child.birth_date || '').trim();
    if (!name && !birthRaw) return;

    if (!name || !birthRaw) {
      errors.push({ index, code: 'incomplete' });
      return;
    }

    const parsed = parseBirthDate(birthRaw);
    if (!parsed.ok) {
      errors.push({ index, code: 'invalid_birth_date' });
      return;
    }

    kept.push({ name, birth_date: parsed.iso });
  });

  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, children: kept };
}
