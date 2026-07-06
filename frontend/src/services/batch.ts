import type { BatchJobResponse } from '../types';
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

  async getJobStatus(jobId: string): Promise<BatchJobResponse> {
    return apiRequest<BatchJobResponse>(`/batch/jobs/${jobId}`);
  },

  async listJobs(): Promise<unknown[]> {
    // @integration-point BATCH_LIST
    return [];
  },
};
