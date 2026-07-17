import { describe, expect, it } from 'vitest';
import {
  detectDocumentKindFromFile,
  detectSlotFromFile,
} from './detectDocumentSlot';

function file(name: string, type = 'application/pdf') {
  return { name, type };
}

describe('detectDocumentKindFromFile', () => {
  it('classifies payslip names that contain the letters id inside other words', () => {
    expect(detectDocumentKindFromFile(file('payslip_valid.png', 'image/png'))).toBe('payslip');
    expect(detectDocumentKindFromFile(file('payslip_valid_2026_06_employee_001.png', 'image/png'))).toBe(
      'payslip',
    );
    expect(detectSlotFromFile(file('payslip_valid.png', 'image/png'))).toBe('payslip');
  });

  it('classifies salary and Hebrew payslip names as payslips', () => {
    expect(detectDocumentKindFromFile(file('salary_2025.pdf'))).toBe('payslip');
    expect(detectDocumentKindFromFile(file('תלוש_שכר.pdf'))).toBe('payslip');
  });

  it('classifies national ID without matching bare id substrings', () => {
    expect(detectDocumentKindFromFile(file('teudat_zehut.png', 'image/png'))).toBe('national_id');
    expect(detectDocumentKindFromFile(file('national_id.pdf'))).toBe('national_id');
    expect(detectDocumentKindFromFile(file('תעודת_זהות.jpg', 'image/jpeg'))).toBe('national_id');
  });

  it('classifies contract, attendance, bank, and tax forms', () => {
    expect(detectDocumentKindFromFile(file('employment_contract.pdf'))).toBe('contract');
    expect(detectDocumentKindFromFile(file('attendance_report.pdf'))).toBe('attendance');
    expect(detectDocumentKindFromFile(file('bank_details.pdf'))).toBe('bank_details');
    expect(detectDocumentKindFromFile(file('tax_form_106.pdf'))).toBe('tax_form');
  });

  it('defaults unlabeled PDF/images to payslip', () => {
    expect(detectDocumentKindFromFile(file('scan.pdf'))).toBe('payslip');
    expect(detectDocumentKindFromFile(file('photo.png', 'image/png'))).toBe('payslip');
  });
});
