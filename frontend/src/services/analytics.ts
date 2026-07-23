import { apiRequest } from './api';
import type {
  AdminOrgCensus,
  AdminQualityAnalytics,
  EmployeeSalaryAnalytics,
  OrgPayrollAnalytics,
  OrgQualityAnalytics,
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

  async orgQuality(year?: number, signal?: AbortSignal): Promise<OrgQualityAnalytics> {
    const query = year != null ? `?year=${year}` : '';
    return apiRequest<OrgQualityAnalytics>(`/analytics/org/quality${query}`, {
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

  async adminQuality(year?: number, signal?: AbortSignal): Promise<AdminQualityAnalytics> {
    const query = year != null ? `?year=${year}` : '';
    return apiRequest<AdminQualityAnalytics>(`/analytics/admin/quality${query}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },
};
