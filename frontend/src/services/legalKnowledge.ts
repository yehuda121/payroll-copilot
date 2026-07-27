import { apiRequest } from './api';

export type VectorIndexHealth = {
  backend: string;
  embedding_model: string | null;
  indexed_rules: number;
  indexed_versions: number;
  chunk_count: number;
  last_indexed_at: string | null;
  last_error: string | null;
  status: string;
};

export type LegalSyncRun = {
  run_id: string;
  trigger: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  sources_checked: number;
  unchanged_count: number;
  irrelevant_change_count: number;
  material_change_count: number;
  new_relevant_count: number;
  uncertain_count: number;
  error_count: number;
  skipped_unconfigured_count: number;
  outcomes: Array<{
    source_id: string;
    classification: string;
    message: string;
    proposal_id: string | null;
    error: string | null;
    content_hash: string | null;
  }>;
  triggered_by: string | null;
};

export type LegalKnowledgeOverview = {
  active_rules: number;
  historical_versions: number;
  watched_sources: number;
  discovery_sources: number;
  pending_changes: number;
  last_sync: LegalSyncRun | null;
  vector_index: VectorIndexHealth;
};

export type LegalRuleRow = {
  rule_id: string;
  title: string;
  current_version: string;
  valid_from: string | null;
  valid_to: string | null;
  scope: string;
  source_coverage: string;
  watched_sources: string[];
  index_status: string;
  validation_readiness?: string;
  validation_readiness_reason?: string;
  required_fields?: string[];
  currently_executed?: string;
};

export type LegalRuleVersion = {
  rule_id: string;
  version: string;
  status: string;
  valid_from: string | null;
  valid_to: string | null;
  scope: string;
  created_at?: string;
  approved_at?: string | null;
  approved_by?: string | null;
};

export type LegalRuleDetail = {
  rule_id: string;
  versions: LegalRuleVersion[];
  active: LegalRuleVersion | null;
  coverage: Record<string, unknown> | null | undefined;
  validation_readiness?: string;
  validation_readiness_reason?: string;
  required_fields?: string[];
  applicability?: string;
  currently_executed?: string;
  source_monitoring_status?: string;
  vector_index_status?: string;
  last_source_sync?: string | null;
};

export type LegalSource = {
  source_id: string;
  provider: string;
  source_type: string;
  url: string | null;
  authority_level: string;
  related_rule_ids: string[];
  enabled: boolean;
  notes: string;
  last_checked_at: string | null;
  last_content_hash: string | null;
};

export type LegalChangeProposal = {
  proposal_id: string;
  source_id: string;
  classification: string;
  affected_rule_ids: string[];
  diff_text: string;
  ai_summary: string;
  reasoning_summary: string;
  candidate_effective_date: string | null;
  confidence: number | null;
  requires_human_review: boolean;
  evidence_references: string[];
  status: string;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_reason: string | null;
  authority_level: string;
  source_url: string | null;
  sync_run_id: string | null;
};

export type LegalProposalDetail = {
  proposal: LegalChangeProposal;
  old_snapshot: string | null;
  new_snapshot: string | null;
};

export type ApproveProposalPayload = {
  effective_date: string;
  confirm_effective_date: boolean;
  rule_yaml_override?: Record<string, unknown>;
  new_rule_id?: string;
  new_rule_body?: Record<string, unknown>;
};

export type RejectProposalPayload = {
  reason?: string;
};

export const legalKnowledgeService = {
  async overview(signal?: AbortSignal): Promise<LegalKnowledgeOverview> {
    return apiRequest<LegalKnowledgeOverview>('/admin/legal-knowledge/overview', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async listRules(signal?: AbortSignal): Promise<LegalRuleRow[]> {
    return apiRequest<LegalRuleRow[]>('/admin/legal-knowledge/rules', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async getRule(ruleId: string, signal?: AbortSignal): Promise<LegalRuleDetail> {
    return apiRequest<LegalRuleDetail>(`/admin/legal-knowledge/rules/${encodeURIComponent(ruleId)}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async listSources(signal?: AbortSignal): Promise<LegalSource[]> {
    return apiRequest<LegalSource[]>('/admin/legal-knowledge/sources', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async triggerSync(
    contentOverrides?: Record<string, string>,
    signal?: AbortSignal,
  ): Promise<LegalSyncRun> {
    return apiRequest<LegalSyncRun>('/admin/legal-knowledge/sync', {
      method: 'POST',
      portalAuth: true,
      signal,
      body: contentOverrides ? JSON.stringify({ content_overrides: contentOverrides }) : undefined,
    });
  },

  async listSyncRuns(limit = 50, signal?: AbortSignal): Promise<LegalSyncRun[]> {
    return apiRequest<LegalSyncRun[]>(`/admin/legal-knowledge/sync/runs?limit=${limit}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async getSyncRun(runId: string, signal?: AbortSignal): Promise<LegalSyncRun> {
    return apiRequest<LegalSyncRun>(
      `/admin/legal-knowledge/sync/runs/${encodeURIComponent(runId)}`,
      {
        method: 'GET',
        portalAuth: true,
        signal,
      },
    );
  },

  async listProposals(statusFilter?: string, signal?: AbortSignal): Promise<LegalChangeProposal[]> {
    const query = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : '';
    return apiRequest<LegalChangeProposal[]>(`/admin/legal-knowledge/proposals${query}`, {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async getProposal(proposalId: string, signal?: AbortSignal): Promise<LegalProposalDetail> {
    return apiRequest<LegalProposalDetail>(
      `/admin/legal-knowledge/proposals/${encodeURIComponent(proposalId)}`,
      {
        method: 'GET',
        portalAuth: true,
        signal,
      },
    );
  },

  async approveProposal(
    proposalId: string,
    payload: ApproveProposalPayload,
    signal?: AbortSignal,
  ): Promise<LegalChangeProposal> {
    return apiRequest<LegalChangeProposal>(
      `/admin/legal-knowledge/proposals/${encodeURIComponent(proposalId)}/approve`,
      {
        method: 'POST',
        portalAuth: true,
        signal,
        body: JSON.stringify(payload),
      },
    );
  },

  async rejectProposal(
    proposalId: string,
    payload: RejectProposalPayload,
    signal?: AbortSignal,
  ): Promise<LegalChangeProposal> {
    return apiRequest<LegalChangeProposal>(
      `/admin/legal-knowledge/proposals/${encodeURIComponent(proposalId)}/reject`,
      {
        method: 'POST',
        portalAuth: true,
        signal,
        body: JSON.stringify(payload),
      },
    );
  },

  async vectorIndexHealth(signal?: AbortSignal): Promise<VectorIndexHealth> {
    return apiRequest<VectorIndexHealth>('/admin/legal-knowledge/vector-index', {
      method: 'GET',
      portalAuth: true,
      signal,
    });
  },

  async rebuildVectorIndex(signal?: AbortSignal): Promise<Record<string, unknown>> {
    return apiRequest<Record<string, unknown>>('/admin/legal-knowledge/vector-index/rebuild', {
      method: 'POST',
      portalAuth: true,
      signal,
    });
  },
};
