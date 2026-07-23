import { apiRequest } from './api';

export type AIDashboardSummary = {
  total_tokens: number;
  tokens_by_provider: Record<string, number>;
  tokens_by_model: Record<string, number>;
  tokens_by_capability: Record<string, number>;
  estimated_cost_usd: number;
  average_latency_ms: number;
  error_rate: number;
  retry_rate: number;
  fallback_rate: number;
  request_count: number;
  window_hours: number;
  prompt_versions: Record<string, number>;
  source: 'cloudwatch' | 'process_local' | string;
};

export type ModelComparisonItem = {
  provider: string;
  model: string;
  capability?: string;
  request_count: number;
  average_latency_ms: number;
  average_tokens: number;
  estimated_cost_usd: number;
  success_rate: number;
  error_rate?: number;
  retry_rate?: number;
  fallback_rate?: number;
};

export type HistoryPoint = {
  timestamp: string;
  value: number;
};

export type ProviderHistoryItem = {
  provider: string;
  tokens: number;
  estimated_cost_usd: number;
  average_latency_ms: number;
  success_count: number;
  error_count: number;
  retry_count: number;
  fallback_count: number;
  request_count: number;
  success_rate: number;
};

export type AIHistorySummary = {
  source: 'cloudwatch' | 'process_local' | string;
  window_hours: number;
  period_seconds: number;
  tokens: HistoryPoint[];
  cost_usd: HistoryPoint[];
  latency_ms: HistoryPoint[];
  successes: HistoryPoint[];
  errors: HistoryPoint[];
  retries: HistoryPoint[];
  fallbacks: HistoryPoint[];
  by_provider: ProviderHistoryItem[];
  prompt_versions: Record<string, number>;
};

export const aiMonitoringService = {
  async dashboard(windowHours = 24, signal?: AbortSignal): Promise<AIDashboardSummary> {
    return apiRequest<AIDashboardSummary>(
      `/admin/ai/dashboard?window_hours=${windowHours}`,
      { method: 'GET', portalAuth: true, signal },
    );
  },

  async modelComparison(
    windowHours = 24,
    signal?: AbortSignal,
  ): Promise<{ items: ModelComparisonItem[]; window_hours?: number }> {
    return apiRequest<{ items: ModelComparisonItem[]; window_hours?: number }>(
      `/admin/ai/models/comparison?window_hours=${windowHours}`,
      { method: 'GET', portalAuth: true, signal },
    );
  },

  async history(windowHours = 24, signal?: AbortSignal): Promise<AIHistorySummary> {
    return apiRequest<AIHistorySummary>(
      `/admin/ai/history?window_hours=${windowHours}`,
      { method: 'GET', portalAuth: true, signal },
    );
  },
};
