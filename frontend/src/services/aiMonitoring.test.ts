import { describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '../services/api';
import { aiMonitoringService } from './aiMonitoring';

describe('aiMonitoringService', () => {
  it('calls dashboard, comparison, and history endpoints', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await aiMonitoringService.dashboard(24);
    expect(apiRequest).toHaveBeenCalledWith('/admin/ai/dashboard?window_hours=24', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await aiMonitoringService.modelComparison(72);
    expect(apiRequest).toHaveBeenCalledWith('/admin/ai/models/comparison?window_hours=72', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await aiMonitoringService.history(6);
    expect(apiRequest).toHaveBeenCalledWith('/admin/ai/history?window_hours=6', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });
  });
});
