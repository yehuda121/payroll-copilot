import { describe, expect, it } from 'vitest';
import { toWritePayload, type EmployeeFormValues } from './EmployeeForm';

const base: EmployeeFormValues = {
  employeeNumber: 'E-1',
  firstName: 'Yehuda',
  lastName: 'Test',
  email: 'keep@example.com',
  nationalId: '',
  employmentType: 'full_time',
  salaryType: 'monthly',
  baseSalaryOrRate: '10000',
  contractStartDate: '2024-01-01',
};

describe('toWritePayload email and national ID', () => {
  it('includes email on create', () => {
    const payload = toWritePayload(base, 'create');
    expect(payload.email).toBe('keep@example.com');
    expect(payload.employee_number).toBe('E-1');
  });

  it('includes email on edit so accountants can update matching address', () => {
    const payload = toWritePayload({ ...base, email: 'new@example.com' }, 'edit');
    expect(payload.email).toBe('new@example.com');
    expect(payload.first_name).toBe('Yehuda');
    expect(payload.last_name).toBe('Test');
    expect(payload.employee_number).toBeUndefined();
  });

  it('includes national_id when provided on edit', () => {
    const payload = toWritePayload({ ...base, nationalId: '000000018' }, 'edit');
    expect(payload.national_id).toBe('000000018');
  });

  it('omits national_id when blank on edit (keep existing)', () => {
    const payload = toWritePayload({ ...base, nationalId: '  ' }, 'edit');
    expect(payload.national_id).toBeUndefined();
  });
});
