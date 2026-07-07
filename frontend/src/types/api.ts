export type ApiError = {
  message: string;
  status: number;
};

export type GuestSessionResponse = {
  guest_token: string;
  expires_at: string;
};

export type ValidationScopeItem = {
  key: string;
  label: string;
  status: 'completed' | 'partial' | 'not_available';
  reason?: string | null;
};

export type UploadedDocumentItem = {
  document_type: string;
  document_id: string;
  uploaded: boolean;
  original_filename?: string | null;
};

export type ValidationFinding = {
  id: string;
  rule_id: string;
  severity: 'info' | 'warning' | 'critical';
  message_key: string;
  expected_value: string | null;
  actual_value: string | null;
  confidence: number;
  legal_reference: string | null;
};

export type ValidationRunRequest = {
  document_id: string;
  supporting_document_ids?: string[];
};

export type ValidationRunResponse = {
  id: string;
  document_id: string;
  status: string;
  overall_result: 'pass' | 'warnings' | 'critical' | null;
  overall_confidence: number | null;
  rules_evaluated: number;
  rules_failed: number;
  checks_passed_count: number;
  validation_confidence: number | null;
  confidence_explanation: string | null;
  validation_scope: ValidationScopeItem[];
  uploaded_documents: UploadedDocumentItem[];
  extraction_connected: boolean;
  findings: ValidationFinding[];
};

export type DocumentUploadResponse = {
  document_id: string;
  status: string;
  processing_job_id?: string | null;
};

export type DocumentResponse = {
  document_id: string;
  document_type: string;
  status: string;
  original_filename: string;
  file_size_bytes: number;
};

export type BatchJobResponse = {
  job_id: string;
  status: string;
};

export type LegalRuleSummary = {
  filename: string;
  rule_count?: number;
};
