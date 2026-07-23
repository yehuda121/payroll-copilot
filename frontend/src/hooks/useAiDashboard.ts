import { useCallback } from 'react';
import { aiMonitoringService } from '../services/aiMonitoring';
import type { AIDashboardSummary } from '../services/aiMonitoring';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useAiDashboard(windowHours: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => aiMonitoringService.dashboard(windowHours, signal),
    [windowHours],
  );
  return useAnalyticsResource<AIDashboardSummary>(
    fetcher,
    [windowHours],
    'Unable to load AI metrics.',
  );
}
