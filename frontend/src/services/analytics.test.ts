import { describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '../services/api';
import { analyticsService } from './analytics';

describe('analyticsService', () => {
  it('calls employee salary endpoint with year query', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({ year: 2026, months: [] });
    await analyticsService.employeeSalary(2026);
    expect(apiRequest).toHaveBeenCalledWith('/analytics/employee/salary?year=2026', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });
  });

  it('calls org payroll and admin census endpoints', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await analyticsService.orgPayroll(2025);
    expect(apiRequest).toHaveBeenCalledWith('/analytics/org/payroll?year=2025', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await analyticsService.adminCensus();
    expect(apiRequest).toHaveBeenCalledWith('/analytics/admin/census', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });
  });

  it('calls org and admin quality endpoints', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await analyticsService.orgQuality(2026);
    expect(apiRequest).toHaveBeenCalledWith('/analytics/org/quality?year=2026', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await analyticsService.adminQuality(2026);
    expect(apiRequest).toHaveBeenCalledWith('/analytics/admin/quality?year=2026', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });
  });
});
