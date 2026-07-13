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
  code: string;
  rule_id: string;
  severity: 'info' | 'warning' | 'critical';
  message_key: string;
  message: string;
  explanation: string;
  expected_value: string | null;
  actual_value: string | null;
  confidence: number;
  legal_reference: string | null;
};

export type ValidationRunRequest = {
  document_id: string;
  supporting_document_ids?: string[];
  locale?: 'he' | 'en' | 'ar';
};

export type ValidationRunResponse = {
  id: string;
  document_id: string;
  status: string;
  locale: string;
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

export type DocumentLanguage = 'he' | 'en' | 'ar' | 'auto';

export type DocumentUploadResponse = {
  document_id: string;
  status: string;
  processing_job_id?: string | null;
  background_status?: string;
  document_language?: DocumentLanguage;
  ocr_language_status?: string;
};

export type DocumentResponse = {
  document_id: string;
  document_type: string;
  status: string;
  original_filename: string;
  file_size_bytes: number;
  document_language?: DocumentLanguage;
  ocr_language_status?: string;
};

export type ExtractedPayslipField = {
  key: string;
  value: unknown;
  confidence: number | null;
  source_text: string | null;
  status: string;
  edited_by_user?: boolean;
  original_value?: unknown;
};

export type GuestPayslipExtractionResponse = {
  document_id: string;
  extraction_id: string;
  extraction_version?: number | null;
  ocr_status: string;
  parser_status: string;
  language: string;
  ocr_engine: string | null;
  parser_model: string | null;
  warnings: string[];
  fields: ExtractedPayslipField[];
  error_message?: string | null;
};

export type GuestExtractionCorrectionRequest = {
  corrections: Array<{
    key: string;
    value?: unknown;
    clear?: boolean;
  }>;
};

export type BatchJobResponse = {
  batch_job_id: string;
  status: string;
};

export type BatchPipelineStage = {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | string;
  detail?: string | null;
};

export type BatchJobStatus = {
  id: string;
  batch_job_id?: string;
  status: string;
  current_stage: string;
  total_slips: number;
  processed_slips: number;
  failed_slips: number;
  progress_percent: number;
  source_filename?: string | null;
  error_message?: string | null;
  report_summary?: Record<string, number>;
  stages: BatchPipelineStage[];
  updated_at?: string | null;
  created_at?: string | null;
};

export type LegalRuleSummary = {
  filename: string;
  version?: string;
  content_hash?: string;
  rules_count?: number;
  rule_count?: number;
};
