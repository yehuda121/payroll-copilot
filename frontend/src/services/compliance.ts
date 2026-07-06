import type { LegalRuleSummary } from '../types';
import { apiRequest } from './api';

/**
 * Compliance, rule packs, and MCP legal sync.
 * @integration-point COMPLIANCE_SERVICE
 */
export const complianceService = {
  async listLegalRules(): Promise<LegalRuleSummary[]> {
    return apiRequest<LegalRuleSummary[]>('/compliance/legal-rules');
  },

  async listDiffProposals(): Promise<unknown[]> {
    // @integration-point COMPLIANCE_DIFFS — GET /compliance/diff-proposals
    return [];
  },

  async listRulePacks(): Promise<unknown[]> {
    // @integration-point RULE_PACKS
    return [];
  },
};
