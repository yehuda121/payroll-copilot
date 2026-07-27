import { describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '../services/api';
import { ragEvaluationService } from './ragEvaluation';

describe('ragEvaluationService', () => {
  it('calls summary and run endpoints', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await ragEvaluationService.summary();
    expect(apiRequest).toHaveBeenCalledWith('/admin/rag-evaluation/summary', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await ragEvaluationService.startRun();
    expect(apiRequest).toHaveBeenCalledWith('/admin/rag-evaluation/runs', {
      method: 'POST',
      portalAuth: true,
      signal: undefined,
    });
  });

  it('calls compare with query params', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await ragEvaluationService.compare('run-a', 'run-b');
    expect(apiRequest).toHaveBeenCalledWith(
      '/admin/rag-evaluation/compare?run_a=run-a&run_b=run-b',
      {
        method: 'GET',
        portalAuth: true,
        signal: undefined,
      },
    );
  });
});
