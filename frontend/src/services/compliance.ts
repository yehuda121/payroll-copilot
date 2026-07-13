import type { LegalRuleSummary } from '../types';
import { apiRequest } from './api';

export type RuleFileContent = {
  filename: string;
  content: string;
  versions: Array<{
    version_id: string;
    filename: string;
    created_at: string;
    reason: string;
    previous_version_id: string | null;
  }>;
};

/**
 * Compliance, rule packs, and MCP legal sync.
 * @integration-point COMPLIANCE_SERVICE
 */
export const complianceService = {
  async listLegalRules(): Promise<LegalRuleSummary[]> {
    return apiRequest<LegalRuleSummary[]>('/compliance/legal-rules');
  },

  async getLegalRule(filename: string): Promise<RuleFileContent> {
    return apiRequest<RuleFileContent>(`/compliance/legal-rules/${encodeURIComponent(filename)}`);
  },

  async updateLegalRule(filename: string, content: string, reason: string): Promise<RuleFileContent> {
    return apiRequest<RuleFileContent>(`/compliance/legal-rules/${encodeURIComponent(filename)}`, {
      method: 'PUT',
      body: JSON.stringify({ content, reason }),
    });
  },

  async rollbackLegalRule(
    filename: string,
    versionId: string,
    reason: string,
  ): Promise<RuleFileContent> {
    return apiRequest<RuleFileContent>(
      `/compliance/legal-rules/${encodeURIComponent(filename)}/rollback`,
      {
        method: 'POST',
        body: JSON.stringify({ version_id: versionId, reason }),
      },
    );
  },

  async listDiffProposals(): Promise<unknown[]> {
    return apiRequest<unknown[]>('/compliance/diff-proposals');
  },

  async listRulePacks(): Promise<unknown[]> {
    return [];
  },
};
