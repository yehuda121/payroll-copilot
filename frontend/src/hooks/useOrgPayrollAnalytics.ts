import { useCallback } from 'react';
import { analyticsService } from '../services/analytics';
import type { OrgPayrollAnalytics } from '../types/analytics';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useOrgPayrollAnalytics(year: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => analyticsService.orgPayroll(year, signal),
    [year],
  );
  return useAnalyticsResource<OrgPayrollAnalytics>(fetcher, [year]);
}
