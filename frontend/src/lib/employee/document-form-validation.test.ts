import { describe, expect, it } from 'vitest';
import { parseBirthDate, normalizeBirthDateInput } from './birth-date';
import { validateNationalId, isValidIsraeliIdChecksum } from './israeli-id';
import { validateAppendixChildren } from './appendix-children-validation';

describe('israeli-id (backend checksum port)', () => {
  it('accepts a known valid id', () => {
    expect(isValidIsraeliIdChecksum('313366783')).toBe(true);
    expect(validateNationalId('313366783')).toEqual({ ok: true, digits: '313366783' });
  });

  it('rejects non-digits, wrong length, and bad checksum', () => {
    expect(validateNationalId('31336678a').ok).toBe(false);
    expect(validateNationalId('12345678').ok).toBe(false);
    expect(validateNationalId('123456789').ok).toBe(false);
  });
});

describe('birth-date', () => {
  it('parses common formats to YYYY-MM-DD', () => {
    expect(parseBirthDate('25.11.1994')).toEqual({ ok: true, iso: '1994-11-25' });
    expect(parseBirthDate('25/11/1994')).toEqual({ ok: true, iso: '1994-11-25' });
    expect(parseBirthDate('1994-11-25')).toEqual({ ok: true, iso: '1994-11-25' });
    expect(normalizeBirthDateInput('1.2.2001')).toBe('2001-02-01');
  });

  it('rejects impossible dates', () => {
    expect(parseBirthDate('31.02.2000').ok).toBe(false);
  });
});

describe('appendix children validation', () => {
  it('drops fully empty rows and keeps complete rows', () => {
    const result = validateAppendixChildren([
      { name: '', birth_date: '' },
      { name: 'נועה', birth_date: '12.03.2015' },
    ]);
    expect(result).toEqual({
      ok: true,
      children: [{ name: 'נועה', birth_date: '2015-03-12' }],
    });
  });

  it('errors when only one field is filled', () => {
    const result = validateAppendixChildren([{ name: 'נועה', birth_date: '' }]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors[0]?.code).toBe('incomplete');
    }
  });
});
