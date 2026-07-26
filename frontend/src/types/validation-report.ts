import type { ValidationRunResponse } from './api';

export type OverallStatusLabel = string;

export type RuleEvaluationOutcome = {
  rule_id: string;
  outcome: 'passed' | 'failed' | 'skipped' | string;
  skip_reason?: string | null;
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
};
