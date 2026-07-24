import type { AppendixChild } from './document-fixed-forms';
import { parseBirthDate } from './birth-date';
import { FIELD_MAX_LENGTH, normalizeHumanText, validatePersonName } from './field-text';

export type AppendixChildRowError = {
  index: number;
  code: 'incomplete' | 'invalid_birth_date' | 'invalid_name' | 'name_digits' | 'name_max_length';
};

export type AppendixChildrenValidation =
  | { ok: true; children: AppendixChild[] }
  | { ok: false; errors: AppendixChildRowError[] };

/**
 * Empty rows (both blank) are dropped.
 * Rows with only one field filled are invalid.
 * Names and birth dates are normalized/validated when present.
 */
export function validateAppendixChildren(children: AppendixChild[]): AppendixChildrenValidation {
  const errors: AppendixChildRowError[] = [];
  const kept: AppendixChild[] = [];

  children.forEach((child, index) => {
    const name = normalizeHumanText(child.name || '');
    const birthRaw = (child.birth_date || '').trim();
    if (!name && !birthRaw) return;

    if (!name || !birthRaw) {
      errors.push({ index, code: 'incomplete' });
      return;
    }

    const nameResult = validatePersonName(name);
    if (!nameResult.ok) {
      if (nameResult.code === 'digits') errors.push({ index, code: 'name_digits' });
      else if (nameResult.code === 'max_length') errors.push({ index, code: 'name_max_length' });
      else errors.push({ index, code: 'invalid_name' });
      return;
    }

    if (name.length > FIELD_MAX_LENGTH.personName) {
      errors.push({ index, code: 'name_max_length' });
      return;
    }

    const parsed = parseBirthDate(birthRaw);
    if (!parsed.ok) {
      errors.push({ index, code: 'invalid_birth_date' });
      return;
    }

    kept.push({ name: nameResult.value, birth_date: parsed.iso });
  });

  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, children: kept };
}
