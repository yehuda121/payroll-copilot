import { describe, expect, it } from 'vitest';
import {
  buildEmployeeFieldValidationMap,
  countValidationStatuses,
} from './field-validation-status';
import type { ExtractedPayslipField } from '../../types/api';
import type { GuestValidationReport } from '../../types/validation-report';

describe('employee field validation status map', () => {
  const fields: ExtractedPayslipField[] = [
    {
      key: 'base_salary',
      value: 10000,
      confidence: 0.9,
      source_text: null,
      status: 'FOUND',
    },
    {
      key: 'travel_expenses',
      value: 200,
      confidence: 0.5,
      source_text: null,
      status: 'UNCERTAIN',
    },
    {
      key: 'vacation_balance',
      value: null,
      confidence: null,
      source_text: null,
      status: 'MISSING',
    },
  ];

  it('maps findings and extraction fallbacks after a validation report', () => {
    const report = {
      runId: 'r1',
      documentId: 'd1',
      overallResult: 'warnings',
      overallStatus: 'Warnings',
      summary: 'Mixed',
      validationConfidence: 0.8,
      confidenceExplanation: null,
      scope: [],
      uploadedDocuments: [],
      checksPassedCount: 1,
      findings: [
        {
          id: 'f1',
          code: 'salary_check',
          rule_id: 'payroll.base_salary',
          severity: 'critical' as const,
          message_key: 'base_salary.mismatch',
          message: 'Salary mismatch',
          explanation: 'Does not match contract',
          expected_value: '12000',
          actual_value: '10000',
          confidence: 0.95,
          legal_reference: null,
        },
      ],
      extractionConnected: true,
    } satisfies GuestValidationReport;

    const map = buildEmployeeFieldValidationMap(fields, report);
    expect(map.base_salary?.status).toBe('failed');
    expect(map.travel_expenses?.status).toBe('uncertain');
    expect(map.vacation_balance?.status).toBe('unchecked');

    const counts = countValidationStatuses(map);
    expect(counts.failed).toBe(1);
    expect(counts.uncertain).toBe(1);
    expect(counts.unchecked).toBe(1);
  });
});
