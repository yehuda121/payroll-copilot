import type { ValidationRunResponse } from './api';

export type OverallStatusLabel = string;

export type RuleEvaluationOutcome = {
  rule_id: string;
  outcome: 'passed' | 'failed' | 'uncertain' | 'not_run' | 'skipped' | string;
  skip_reason?: string | null;
  reason_code?: string | null;
  message?: string | null;
};

export type ManualApprovalMeta = {
  finding_id?: string | null;
  rule_id?: string | null;
  original_severity?: string | null;
  original_deterministic_status?: string | null;
  deterministic_status?: string | null;
  review_status?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  reason?: string | null;
  validation_run_id?: string | null;
};

export type GuestValidationReport = {
  runId: string;
  documentId: string;
  overallResult: 'pass' | 'warnings' | 'critical' | null;
  overallStatus: OverallStatusLabel;
  summary: string;
  validationConfidence: number | null;
  confidenceExplanation: string | null;
  scope: ValidationRunResponse['validation_scope'];
  uploadedDocuments: ValidationRunResponse['uploaded_documents'];
  checksPassedCount: number;
  findings: ValidationRunResponse['findings'];
  extractionConnected: boolean;
  /** Authoritative per-rule outcomes when the run persisted them. */
  ruleOutcomes?: RuleEvaluationOutcome[];
  /** Human review overlays — never rewrite deterministic outcomes. */
  manualApprovals?: ManualApprovalMeta[];
};
