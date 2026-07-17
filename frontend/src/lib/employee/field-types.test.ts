import { describe, expect, it } from 'vitest';
import {
  detectEmployeeFieldType,
  formatFieldPreview,
  normalizeFieldInput,
  fieldSpansColumns,
} from './field-types';

describe('employee field types', () => {
  it('detects common payroll types', () => {
    expect(detectEmployeeFieldType('base_salary', 10000)).toBe('currency');
    expect(detectEmployeeFieldType('regular_hours', 160)).toBe('number');
    expect(detectEmployeeFieldType('pay_period', '06/2026')).toBe('date');
    expect(detectEmployeeFieldType('messages', 'a\nb')).toBe('multiline_text');
    expect(detectEmployeeFieldType('custom_note', { rows: [] })).toBe('table');
    expect(detectEmployeeFieldType('weird_custom', null)).toBe('unknown');
  });

  it('truncates long previews and spans wide fields', () => {
    const long = 'x'.repeat(120);
    expect(formatFieldPreview(long, 'multiline_text', 'en').endsWith('…')).toBe(true);
    expect(fieldSpansColumns('multiline_text')).toBe(2);
    expect(fieldSpansColumns('number')).toBe(1);
    expect(fieldSpansColumns('text', long)).toBe(2);
    expect(fieldSpansColumns('text', 'short')).toBe(1);
  });

  it('normalizes and rejects extreme values client-side', () => {
    expect(normalizeFieldInput('  12.5  ', 'number')).toEqual({ ok: true, value: '12.5' });
    expect(normalizeFieldInput('abc', 'number').ok).toBe(false);
    expect(normalizeFieldInput('x'.repeat(9000), 'text').ok).toBe(false);
  });
});
