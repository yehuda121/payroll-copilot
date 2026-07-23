import { apiRequest } from './api';

export type AIDashboardSummary = {
  total_tokens: number;
  tokens_by_provider: Record<string, number>;
  tokens_by_model: Record<string, number>;
  estimated_cost_usd: number;
  average_latency_ms: number;
  error_rate: number;
  retry_rate: number;
  fallback_rate: number;
  request_count: number;
  window_hours: number;
};

export type ModelComparisonItem = {
  provider: string;
  model: string;
  request_count: number;
  average_latency_ms: number;
  average_tokens: number;
  estimated_cost_usd: number;
  success_rate: number;
};

export const aiMonitoringService = {
  async dashboard(windowHours = 24): Promise<AIDashboardSummary> {
    return apiRequest<AIDashboardSummary>(
      `/admin/ai/dashboard?window_hours=${windowHours}`,
      { method: 'GET', portalAuth: true },
    );
  },

  async modelComparison(windowHours = 24): Promise<{ items: ModelComparisonItem[] }> {
    return apiRequest<{ items: ModelComparisonItem[] }>(
      `/admin/ai/models/comparison?window_hours=${windowHours}`,
      { method: 'GET', portalAuth: true },
    );
  },
};
