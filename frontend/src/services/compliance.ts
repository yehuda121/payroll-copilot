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

  async checkLegalUpdates(body?: {
    candidates?: Array<{
      rule_id: string;
      parameter_key: string;
      proposed_value: unknown;
      legal_source: string;
      effective_date?: string | null;
      explanation?: string;
      rule_name?: string | null;
    }>;
    external_text_by_source?: Record<string, string>;
  }): Promise<LegalUpdateCheckResult> {
    return apiRequest<LegalUpdateCheckResult>('/compliance/check-legal-updates', {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    });
  },

  async applyLegalUpdates(body: {
    selected_change_ids: string[];
    effective_changes: LegalRuleDifference[];
    future_changes: LegalRuleDifference[];
  }): Promise<{ created_versions: unknown[]; skipped_change_ids: string[] }> {
    return apiRequest('/compliance/apply-legal-updates', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};

export type LegalRuleDifference = {
  change_id: string;
  rule_id: string;
  rule_name: string;
  parameter_key: string;
  current_value: unknown;
  proposed_value: unknown;
  legal_source: string;
  effective_date: string | null;
  explanation: string;
  selectable: boolean;
  kind: string;
};

export type LegalUpdateCheckResult = {
  status: 'up_to_date' | 'differences_found' | string;
  message: string;
  local_bundle_version: string;
  checked_at: string;
  effective_changes: LegalRuleDifference[];
  future_changes: LegalRuleDifference[];
};
