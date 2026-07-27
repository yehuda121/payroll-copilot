import { describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '../services/api';
import { legalKnowledgeService } from './legalKnowledge';

describe('legalKnowledgeService', () => {
  it('calls overview and rules endpoints', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await legalKnowledgeService.overview();
    expect(apiRequest).toHaveBeenCalledWith('/admin/legal-knowledge/overview', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });

    await legalKnowledgeService.listRules();
    expect(apiRequest).toHaveBeenCalledWith('/admin/legal-knowledge/rules', {
      method: 'GET',
      portalAuth: true,
      signal: undefined,
    });
  });

  it('calls proposal approve with payload', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});
    await legalKnowledgeService.approveProposal('p1', {
      effective_date: '2026-01-01',
      confirm_effective_date: true,
    });
    expect(apiRequest).toHaveBeenCalledWith('/admin/legal-knowledge/proposals/p1/approve', {
      method: 'POST',
      portalAuth: true,
      signal: undefined,
      body: JSON.stringify({
        effective_date: '2026-01-01',
        confirm_effective_date: true,
      }),
    });
  });
});
