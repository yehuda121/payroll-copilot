import { useCallback } from 'react';
import { analyticsService } from '../services/analytics';
import type { EmployeeSalaryAnalytics } from '../types/analytics';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useEmployeeSalaryAnalytics(year: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => analyticsService.employeeSalary(year, signal),
    [year],
  );
  return useAnalyticsResource<EmployeeSalaryAnalytics>(fetcher, [year]);
}
