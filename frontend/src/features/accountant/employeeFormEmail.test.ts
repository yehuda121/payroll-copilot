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

describe('toWritePayload email immutability', () => {
  it('includes email on create', () => {
    const payload = toWritePayload(base, 'create');
    expect(payload.email).toBe('keep@example.com');
    expect(payload.employee_number).toBe('E-1');
  });

  it('omits email on edit', () => {
    const payload = toWritePayload(base, 'edit');
    expect(payload.email).toBeUndefined();
    expect(payload.first_name).toBe('Yehuda');
    expect(payload.last_name).toBe('Test');
  });
});
