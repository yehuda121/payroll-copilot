import { useCallback } from 'react';
import { analyticsService } from '../services/analytics';
import type { AdminOrgCensus } from '../types/analytics';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useAdminOrgCensus() {
  const fetcher = useCallback(
    (signal: AbortSignal) => analyticsService.adminCensus(signal),
    [],
  );
  return useAnalyticsResource<AdminOrgCensus>(fetcher, []);
}
