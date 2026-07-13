import type {
  BatchJobResponse,
  BatchJobStatus,
} from '../types/api';
import { apiRequest } from './api';

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
    });
  },

  async getJobStatus(jobId: string): Promise<BatchJobStatus> {
    return apiRequest<BatchJobStatus>(`/batch/jobs/${jobId}`);
  },

  async listJobs(): Promise<BatchJobStatus[]> {
    return apiRequest<BatchJobStatus[]>('/batch/jobs');
  },

  async getReport(jobId: string): Promise<{ summary: Record<string, number>; items: unknown[] }> {
    return apiRequest(`/batch/jobs/${jobId}/report`);
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
