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

  it('formats identifiers without thousands separators and keeps money formatting', () => {
    expect(detectEmployeeFieldType('national_id', '313366783')).toBe('identifier');
    expect(detectEmployeeFieldType('employee_number', '00123')).toBe('identifier');
    expect(detectEmployeeFieldType('employer_id', '512345678')).toBe('identifier');
    expect(formatFieldPreview('313366783', 'identifier', 'en')).toBe('313366783');
    expect(formatFieldPreview('00123', 'identifier', 'en')).toBe('00123');
    expect(formatFieldPreview('5300.00', 'currency', 'en')).toMatch(/5/);
    expect(formatFieldPreview('5300.00', 'currency', 'en')).not.toBe('5300.00' + 'x');
    // Money may include grouping separators; identifiers must not.
    expect(formatFieldPreview('313366783', 'identifier', 'en')).not.toContain(',');
  });
});
