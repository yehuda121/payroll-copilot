import { useCallback } from 'react';
import { aiMonitoringService } from '../services/aiMonitoring';
import type { ModelComparisonItem } from '../services/aiMonitoring';
import { useAnalyticsResource } from './useAnalyticsResource';

export function useAiModelComparison(windowHours: number) {
  const fetcher = useCallback(
    async (signal: AbortSignal) => {
      const data = await aiMonitoringService.modelComparison(windowHours, signal);
      return data.items ?? [];
    },
    [windowHours],
  );
  return useAnalyticsResource<ModelComparisonItem[]>(
    fetcher,
    [windowHours],
    'Unable to load model comparison.',
  );
}
