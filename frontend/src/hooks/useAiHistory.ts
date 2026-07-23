import { useCallback } from 'react';
import { aiMonitoringService } from '../services/aiMonitoring';
import type { AIHistorySummary } from '../services/aiMonitoring';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useAiHistory(windowHours: number) {
  const fetcher = useCallback(
    (signal: AbortSignal) => aiMonitoringService.history(windowHours, signal),
    [windowHours],
  );
  return useAnalyticsResource<AIHistorySummary>(
    fetcher,
    [windowHours],
    'Unable to load AI history.',
  );
}
