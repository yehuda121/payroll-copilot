import { useCallback } from 'react';
import { analyticsService } from '../services/analytics';
import type { AdminQualityAnalytics } from '../types/analytics';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useAdminQualityAnalytics(year: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => analyticsService.adminQuality(year, signal),
    [year],
  );
  return useAnalyticsResource<AdminQualityAnalytics>(fetcher, [year]);
}
