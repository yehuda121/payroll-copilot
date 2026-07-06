import type { EmployeeRecord } from '../types';

/**
 * Employee master data management.
 * @integration-point EMPLOYEES_SERVICE
 */
export const employeesService = {
  async list(): Promise<EmployeeRecord[]> {
    // @integration-point EMPLOYEES_LIST — GET /employees
    return [];
  },

  async getByNumber(_employeeNumber: string): Promise<EmployeeRecord | null> {
    // @integration-point EMPLOYEES_GET
    return null;
  },

  async create(_employee: Omit<EmployeeRecord, 'employeeNumber'>): Promise<EmployeeRecord> {
    // @integration-point EMPLOYEES_CREATE — POST /employees
    throw new Error('Employee creation API is not connected.');
  },

  async update(
    _employeeNumber: string,
    _employee: Partial<EmployeeRecord>,
  ): Promise<EmployeeRecord> {
    // @integration-point EMPLOYEES_UPDATE
    throw new Error('Employee update API is not connected.');
  },

  async importExcel(_file: File): Promise<{ imported: number }> {
    // @integration-point EMPLOYEES_IMPORT — POST /employees/import
    throw new Error('Employee Excel import API is not connected.');
  },
};
