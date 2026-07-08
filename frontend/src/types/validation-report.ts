import type { ValidationRunResponse } from './api';

export type OverallStatusLabel = string;

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
};
