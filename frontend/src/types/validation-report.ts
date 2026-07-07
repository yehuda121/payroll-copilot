import type { ValidationRunResponse } from './api';

export type OverallStatusLabel = 'Passed' | 'Passed with Warnings' | 'Action Required' | 'Pending';

export type GuestValidationReport = {
  runId: string;
  documentId: string;
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
