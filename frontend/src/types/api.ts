export type ApiError = {
  message: string;
  status: number;
};

export type GuestSessionResponse = {
  guest_token: string;
  expires_at: string;
};

export type ValidationRunRequest = {
  document_id: string;
};

export type ValidationRunResponse = {
  status: string;
  findings: unknown[];
};

export type DocumentUploadResponse = {
  document_id: string;
  status: string;
};

export type BatchJobResponse = {
  job_id: string;
  status: string;
};

export type LegalRuleSummary = {
  filename: string;
  rule_count?: number;
};
