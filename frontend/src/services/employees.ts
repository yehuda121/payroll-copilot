import { apiRequest } from './api';
import type {
  AuditLogItem,
  DocumentTypeCatalogItem,
  EmployeeRecord,
  EmployeeWritePayload,
  ValidationModuleCatalogItem,
} from '../types/employee';

type ApiEmployee = {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email?: string | null;
  department?: string | null;
  department_id?: string;
  employment_type: EmployeeRecord['employmentType'];
  salary_type: EmployeeRecord['salaryType'];
  base_salary_or_rate?: number | null;
  status: EmployeeRecord['status'];
  national_id_masked?: string | null;
  contract_start_date?: string;
  contract_end_date?: string | null;
  metadata?: Record<string, unknown>;
};

function mapEmployee(row: ApiEmployee): EmployeeRecord {
  return {
    id: row.id,
    employeeNumber: row.employee_number,
    fullName: row.full_name,
    firstName: row.first_name,
    lastName: row.last_name,
    email: row.email ?? '',
    department: row.department ?? 'General',
    departmentId: row.department_id,
    employmentType: row.employment_type,
    salaryType: row.salary_type,
    baseSalaryOrRate: row.base_salary_or_rate ?? 0,
    status: row.status,
    nationalIdMasked: row.national_id_masked,
    contractStartDate: row.contract_start_date,
    contractEndDate: row.contract_end_date,
    metadata: row.metadata,
  };
}

/**
 * Employee master data management (business records — not auth users).
 * @integration-point EMPLOYEES_SERVICE
 */
export const employeesService = {
  async list(params?: {
    q?: string;
    status?: string;
    includeDisabled?: boolean;
  }): Promise<EmployeeRecord[]> {
    const query = new URLSearchParams();
    if (params?.q) query.set('q', params.q);
    if (params?.status) query.set('status', params.status);
    if (params?.includeDisabled === false) query.set('include_disabled', 'false');
    const suffix = query.toString() ? `?${query.toString()}` : '';
    const rows = await apiRequest<ApiEmployee[]>(`/employees${suffix}`, { portalAuth: true });
    return rows.map(mapEmployee);
  },

  async getByNumber(employeeNumber: string): Promise<EmployeeRecord | null> {
    try {
      const row = await apiRequest<ApiEmployee>(`/employees/${encodeURIComponent(employeeNumber)}`, {
        portalAuth: true,
      });
      return mapEmployee(row);
    } catch {
      return null;
    }
  },

  async create(payload: EmployeeWritePayload & { employee_number: string }): Promise<EmployeeRecord> {
    const row = await apiRequest<ApiEmployee>('/employees', {
      method: 'POST',
      body: JSON.stringify(payload),
      portalAuth: true,
    });
    return mapEmployee(row);
  },

  async update(employeeNumber: string, payload: EmployeeWritePayload): Promise<EmployeeRecord> {
    const row = await apiRequest<ApiEmployee>(`/employees/${encodeURIComponent(employeeNumber)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      portalAuth: true,
    });
    return mapEmployee(row);
  },

  async disable(employeeNumber: string): Promise<EmployeeRecord> {
    const row = await apiRequest<ApiEmployee>(
      `/employees/${encodeURIComponent(employeeNumber)}/disable`,
      { method: 'POST', portalAuth: true },
    );
    return mapEmployee(row);
  },

  async matchNationalId(nationalId: string): Promise<{ matched: boolean; employee: EmployeeRecord | null }> {
    const result = await apiRequest<{ matched: boolean; employee: ApiEmployee | null }>(
      '/employees/match/national-id',
      {
        method: 'POST',
        body: JSON.stringify({ national_id: nationalId }),
        portalAuth: true,
      },
    );
    return {
      matched: result.matched,
      employee: result.employee ? mapEmployee(result.employee) : null,
    };
  },

  async getProfile(employeeNumber: string): Promise<Record<string, unknown>> {
    return apiRequest<Record<string, unknown>>(
      `/employees/${encodeURIComponent(employeeNumber)}/profile`,
      { portalAuth: true },
    );
  },

  async importExcel(_file: File): Promise<{ imported: number }> {
    throw new Error('Employee Excel import API is not connected yet.');
  },
};

export const catalogService = {
  async documentTypes(): Promise<DocumentTypeCatalogItem[]> {
    return apiRequest<DocumentTypeCatalogItem[]>('/catalog/document-types');
  },
  async validationModules(): Promise<ValidationModuleCatalogItem[]> {
    return apiRequest<ValidationModuleCatalogItem[]>('/catalog/validation-modules');
  },
};

export const auditLogsService = {
  async list(limit = 100): Promise<AuditLogItem[]> {
    return apiRequest<AuditLogItem[]>(`/audit-logs?limit=${limit}`, {
      portalAuth: true,
    });
  },
};
