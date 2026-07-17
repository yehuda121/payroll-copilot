import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  createBlankEntry,
  entriesFromExtractionResponse,
  getDynamicEntryDisplayKey,
  hasUsableDynamicEntries,
  hasUsableExtractedFields,
  isDocumentOriginEntry,
} from '../../../lib/guest/extraction-review';
import type { DynamicDocumentEntry, GuestPayslipExtractionResponse } from '../../../types/api';

const t = ((key: string) => {
  if (key === 'payroll.fields.unknown') return '(Unknown)';
  if (key === 'payroll.fields.employee_name') return 'Employee Name';
  if (key === 'payroll.fields.gross_salary') return 'Gross Salary';
  return key;
}) as TFunction;

describe('dynamic landing extraction helpers', () => {
  it('detects usable dynamic entries by value presence', () => {
    const entries: DynamicDocumentEntry[] = [
      {
        id: '1',
        key: 'Employee Name',
        value: 'Dana Levi',
        confidence: 0.9,
        page: 1,
        source: 'ocr',
        source_text: 'Dana Levi',
      },
      createBlankEntry(),
    ];
    expect(hasUsableDynamicEntries(entries)).toBe(true);
    expect(hasUsableDynamicEntries([createBlankEntry()])).toBe(false);
    expect(
      hasUsableDynamicEntries([
        {
          id: '2',
          key: 'Employee Number',
          value: '',
          confidence: 0.4,
          page: 1,
          source: 'ocr',
          source_text: null,
        },
      ]),
    ).toBe(false);
  });

  it('keeps unlabeled values and labeled empty values as document-origin', () => {
    expect(
      isDocumentOriginEntry({
        id: 'a',
        key: '',
        value: '12345',
        confidence: 0.5,
        page: 1,
        source: 'ocr',
        source_text: null,
      }),
    ).toBe(true);
    expect(
      isDocumentOriginEntry({
        id: 'b',
        key: 'Employee Number',
        value: '',
        confidence: 0.5,
        page: 1,
        source: 'ocr',
        source_text: null,
      }),
    ).toBe(true);
    expect(isDocumentOriginEntry(createBlankEntry())).toBe(false);
    expect(
      isDocumentOriginEntry({
        id: 'c',
        key: 'national_id',
        value: null,
        confidence: null,
        page: null,
        source: 'ocr',
        source_text: null,
      }),
    ).toBe(false);
  });

  it('never synthesizes empty canonical schema rows from legacy fields', () => {
    const response: GuestPayslipExtractionResponse = {
      document_id: 'd1',
      extraction_id: 'e1',
      ocr_status: 'completed',
      parser_status: 'completed',
      language: 'en',
      ocr_engine: 'tesseract',
      parser_model: 'test',
      warnings: [],
      fields: [
        {
          key: 'employee_name',
          value: 'Dana',
          status: 'FOUND',
          confidence: 0.9,
          source_text: 'Dana',
        },
        {
          key: 'national_id',
          value: null,
          status: 'MISSING',
          confidence: null,
          source_text: null,
        },
        {
          key: 'vacation_balance',
          value: null,
          status: 'MISSING',
          confidence: null,
          source_text: null,
        },
      ],
    };
    const entries = entriesFromExtractionResponse(response);
    expect(entries).toHaveLength(1);
    expect(entries[0]?.key).toBe('employee_name');
  });

  it('prefers dynamic entries and localizes canonical keys for display', () => {
    const response: GuestPayslipExtractionResponse = {
      document_id: 'd1',
      extraction_id: 'e1',
      ocr_status: 'completed',
      parser_status: 'completed',
      language: 'en',
      ocr_engine: 'tesseract',
      parser_model: 'test',
      warnings: [],
      fields: [],
      entries: [
        {
          id: '1',
          key: 'employee_name',
          value: 'Dana',
          confidence: 0.9,
          page: 1,
          source: 'ocr',
          source_text: null,
        },
        {
          id: '2',
          key: 'File Number',
          value: '99',
          confidence: 0.8,
          page: 1,
          source: 'ocr',
          source_text: null,
        },
      ],
    };
    const entries = entriesFromExtractionResponse(response);
    expect(entries).toHaveLength(2);
    expect(getDynamicEntryDisplayKey('employee_name', t)).toBe('Employee Name');
    expect(getDynamicEntryDisplayKey('File Number', t)).toBe('File Number');
    expect(getDynamicEntryDisplayKey('', t)).toBe('(Unknown)');
  });

  it('keeps legacy field usability helper for employee portal', () => {
    expect(
      hasUsableExtractedFields([
        { key: 'gross_salary', value: 12000, status: 'FOUND', confidence: 0.9, source_text: null },
      ]),
    ).toBe(true);
  });
});
