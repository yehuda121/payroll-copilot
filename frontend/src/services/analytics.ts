import { apiRequest } from './api';
import type {
  AdminOrgCensus,
  EmployeeSalaryAnalytics,
  OrgPayrollAnalytics,
} from '../types/analytics';

export const analyticsService = {
  async employeeSalary(year?: number, signal?: AbortSignal): Promise<EmployeeSalaryAnalytics> {
    const query = year != null ? `?year=${year}` : '';
    return apiRequest<EmployeeSalaryAnalytics>(`/analytics/employee/salary${query}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async orgPayroll(year?: number, signal?: AbortSignal): Promise<OrgPayrollAnalytics> {
    const query = year != null ? `?year=${year}` : '';
    return apiRequest<OrgPayrollAnalytics>(`/analytics/org/payroll${query}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async adminCensus(signal?: AbortSignal): Promise<AdminOrgCensus> {
    return apiRequest<AdminOrgCensus>('/analytics/admin/census', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },
};
