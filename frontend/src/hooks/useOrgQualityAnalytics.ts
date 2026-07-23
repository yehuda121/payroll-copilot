import { useCallback } from 'react';
import { analyticsService } from '../services/analytics';
import type { OrgQualityAnalytics } from '../types/analytics';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useOrgQualityAnalytics(year: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => analyticsService.orgQuality(year, signal),
    [year],
  );
  return useAnalyticsResource<OrgQualityAnalytics>(fetcher, [year]);
}
