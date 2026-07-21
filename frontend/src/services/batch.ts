import type {
  BatchExtractedEmployee,
  BatchJobResponse,
  BatchJobStatus,
} from '../types/api';
import { apiRequest } from './api';
import { env } from '../config/env';
import { getPortalAuthHeaders } from '../lib/auth/access-token';
import type { ExtractedPayslipField, DynamicDocumentEntry } from '../types/api';

export type BatchValidationHistoryRun = {
  validation_run_id: string;
  status: string;
  overall_result: string | null;
  confidence: number | null;
  completed_at: string | null;
  extraction_id: string | null;
  outdated: boolean;
  evidence_summary?: {
    result: string | null;
    reason: string;
    extracted_field_count: number;
    evidence_supported_field_count: number;
  };
  findings: Array<{
    id: string;
    rule_id: string;
    category: string;
    severity: string;
    message_key: string;
    message_params: Record<string, unknown>;
    expected_value: string | null;
    actual_value: string | null;
    confidence: number | null;
    evidence_explanation?: {
      available: boolean;
      result: 'passed' | 'failed' | 'uncertain' | string;
      reason: string;
      field_key?: string | null;
      candidate_id?: string | null;
      page?: number | null;
      label?: string | null;
      value?: unknown;
      association_strategy?: string | null;
      association_confidence?: string | null;
      conflict?: boolean;
    };
  }>;
};

export type BatchItemReview = {
  item: BatchExtractedEmployee;
  document_id: string;
  original_filename: string;
  uploaded_at: string | null;
  fields: ExtractedPayslipField[];
  entries?: DynamicDocumentEntry[];
  extraction_id: string | null;
  extraction_version: number | null;
  validation_history: BatchValidationHistoryRun[];
  explainability_enabled?: boolean;
};

/**
 * Bulk payroll batch processing for accountants.
 * @integration-point BATCH_SERVICE
 */
export const batchService = {
  async uploadBulkPdf(file: File): Promise<BatchJobResponse> {
    const formData = new FormData();
    formData.append('file', file);

    return apiRequest<BatchJobResponse>('/batch/payslips', {
      method: 'POST',
      body: formData,
      rawBody: true,
      portalAuth: true,
    });
  },

  async getJobStatus(jobId: string): Promise<BatchJobStatus> {
    return apiRequest<BatchJobStatus>(`/batch/jobs/${jobId}`, { portalAuth: true });
  },

  async listJobs(): Promise<BatchJobStatus[]> {
    return apiRequest<BatchJobStatus[]>('/batch/jobs', { portalAuth: true });
  },

  async getReport(
    jobId: string,
  ): Promise<{ summary: Record<string, number>; items: BatchExtractedEmployee[] }> {
    return apiRequest(`/batch/jobs/${jobId}/report`, { portalAuth: true });
  },

  async resolveItem(
    jobId: string,
    itemId: string,
    payload:
      | { action: 'ignore' }
      | { action: 'edit_national_id'; national_id: string }
      | { action: 'attach_employee'; employee_number: string },
  ): Promise<BatchExtractedEmployee> {
    return apiRequest<BatchExtractedEmployee>(
      `/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/resolve`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
        portalAuth: true,
      },
    );
  },

  async publishItem(
    jobId: string,
    itemId: string,
  ): Promise<{
    document_id: string;
    employee_number: string;
    payroll_year: number;
    payroll_month: number;
    published_at: string;
    validation_run_id: string;
    publication_status: 'published';
  }> {
    return apiRequest(
      `/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/publish`,
      { method: 'POST', portalAuth: true },
    );
  },

  async getItemReview(jobId: string, itemId: string): Promise<BatchItemReview> {
    return apiRequest<BatchItemReview>(
      `/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/review`,
      { portalAuth: true },
    );
  },

  async correctItemReview(
    jobId: string,
    itemId: string,
    corrections: Array<{ key: string; value: unknown; clear?: boolean }>,
  ): Promise<BatchItemReview> {
    return apiRequest<BatchItemReview>(
      `/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/review`,
      {
        method: 'PUT',
        body: JSON.stringify({ corrections }),
        portalAuth: true,
      },
    );
  },

  async validateItemReview(jobId: string, itemId: string): Promise<BatchItemReview> {
    return apiRequest<BatchItemReview>(
      `/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/validate`,
      { method: 'POST', portalAuth: true },
    );
  },

  async getItemContent(jobId: string, itemId: string, signal?: AbortSignal): Promise<Blob> {
    const response = await fetch(
      `${env.apiBaseUrl}/batch/jobs/${encodeURIComponent(jobId)}/items/${encodeURIComponent(itemId)}/content`,
      { headers: getPortalAuthHeaders(), signal },
    );
    if (!response.ok) throw new Error(`Failed to load source document (${response.status})`);
    return response.blob();
  },
};

export type ManualReviewItem = {
  id: string;
  reason: string;
  status: string;
  batch_job_id: string | null;
  national_id_masked: string | null;
  extracted_fields: Record<string, unknown>;
  confidence: number | null;
  resolution_notes: string | null;
  created_at: string;
  resolved_at: string | null;
};

export const manualReviewService = {
  async list(pendingOnly = true): Promise<ManualReviewItem[]> {
    return apiRequest<ManualReviewItem[]>(`/manual-review?pending_only=${pendingOnly}`);
  },

  async resolve(
    itemId: string,
    status: 'resolved_create' | 'resolved_attach' | 'dismissed',
    notes?: string,
  ): Promise<ManualReviewItem> {
    return apiRequest<ManualReviewItem>(`/manual-review/${encodeURIComponent(itemId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ status, notes }),
    });
  },
};
