import { describe, expect, it } from 'vitest';
import { FIELD_MAX_LENGTH, validatePersonName } from '../employee/field-text';
import {
  EMAIL_MAX_LENGTH,
  isValidEmailFormat,
  sanitizeEmailInput,
  validateEmailFormat,
} from './email';
import { clampFreeTextInput, FREE_TEXT_MAX_LENGTH } from './free-text';
import { leaveContactErrorKey, validateLeaveContactFields } from './leave-contact';

describe('shared email validation', () => {
  it('trims and accepts structural emails', () => {
    expect(sanitizeEmailInput('  ada@example.com ')).toBe('ada@example.com');
    expect(validateEmailFormat('ada@example.com').ok).toBe(true);
    expect(isValidEmailFormat('', true)).toBe(true);
  });

  it('rejects malformed and oversized values', () => {
    expect(validateEmailFormat('abc').ok).toBe(false);
    expect(validateEmailFormat('abc@').ok).toBe(false);
    expect(validateEmailFormat('@domain.com').ok).toBe(false);
    expect(validateEmailFormat('abc@domain').ok).toBe(false);
    expect(validateEmailFormat('abc domain@example.com').ok).toBe(false);
    expect(validateEmailFormat(`${'a'.repeat(EMAIL_MAX_LENGTH)}@x.com`).ok).toBe(false);
  });
});

describe('leave contact validation', () => {
  it('allows empty optional contact fields', () => {
    expect(
      validateLeaveContactFields({
        employeeEmail: '',
        employeeName: '',
        startDate: '2026-01-01',
        endDate: '2026-01-02',
      }).ok,
    ).toBe(true);
  });

  it('rejects bad email/name and maps i18n keys', () => {
    const badEmail = validateLeaveContactFields({
      employeeEmail: 'nope',
      employeeName: '',
      startDate: '',
      endDate: '',
    });
    expect(badEmail.ok).toBe(false);
    if (!badEmail.ok) expect(leaveContactErrorKey(badEmail.code)).toBe('common.validation.invalidEmail');

    const badName = validateLeaveContactFields({
      employeeEmail: '',
      employeeName: 'Ada123',
      startDate: '',
      endDate: '',
    });
    expect(badName.ok).toBe(false);
    if (!badName.ok) expect(leaveContactErrorKey(badName.code)).toBe('common.validation.nameNoDigits');
  });
});

describe('person name max length policy', () => {
  it('enforces 50 characters', () => {
    expect(FIELD_MAX_LENGTH.personName).toBe(50);
    expect(validatePersonName('a'.repeat(50)).ok).toBe(true);
    expect(validatePersonName('a'.repeat(51)).ok).toBe(false);
  });
});

describe('free text clamp', () => {
  it('strips controls and clamps length without mutating password spaces', () => {
    expect(clampFreeTextInput('hi\u0000there', 20)).toBe('hithere');
    expect(clampFreeTextInput('x'.repeat(10), 4)).toBe('xxxx');
    expect(FREE_TEXT_MAX_LENGTH.password).toBe(128);
  });
});
