/** Client-side validation helpers for leave manual/edit forms (presentation gate only). */

import { FIELD_MAX_LENGTH, normalizeHumanText, validatePersonName } from '../employee/field-text';
import { sanitizeEmailInput, validateEmailFormat } from './email';

export type LeavePersonContactValues = {
  employeeEmail: string;
  employeeName: string;
  startDate: string;
  endDate: string;
};

export type LeaveContactValidationResult =
  | { ok: true; values: LeavePersonContactValues }
  | { ok: false; code: 'invalid_email' | 'invalid_name' | 'name_digits' | 'name_max_length' };

export function validateLeaveContactFields(
  values: LeavePersonContactValues,
): LeaveContactValidationResult {
  const emailResult = validateEmailFormat(values.employeeEmail, { allowEmpty: true });
  if (!emailResult.ok) return { ok: false, code: 'invalid_email' };

  const nameRaw = values.employeeName.trim();
  if (nameRaw) {
    const nameResult = validatePersonName(nameRaw);
    if (!nameResult.ok) {
      if (nameResult.code === 'digits') return { ok: false, code: 'name_digits' };
      if (nameResult.code === 'max_length') return { ok: false, code: 'name_max_length' };
      return { ok: false, code: 'invalid_name' };
    }
    return {
      ok: true,
      values: {
        employeeEmail: emailResult.value,
        employeeName: nameResult.value,
        startDate: values.startDate,
        endDate: values.endDate,
      },
    };
  }

  return {
    ok: true,
    values: {
      employeeEmail: emailResult.value,
      employeeName: normalizeHumanText(values.employeeName),
      startDate: values.startDate,
      endDate: values.endDate,
    },
  };
}

export function leaveContactErrorKey(
  code: 'invalid_email' | 'invalid_name' | 'name_digits' | 'name_max_length',
): string {
  switch (code) {
    case 'invalid_email':
      return 'common.validation.invalidEmail';
    case 'name_digits':
      return 'common.validation.nameNoDigits';
    case 'name_max_length':
      return 'common.validation.nameMaxLength';
    default:
      return 'common.validation.nameInvalid';
  }
}

export { FIELD_MAX_LENGTH, sanitizeEmailInput };
