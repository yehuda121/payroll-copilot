import type { ValidationRunRequest, ValidationRunResponse } from '../types';
import { apiRequest } from './api';

/**
 * Deterministic validation runs — backend decides pass/fail, not AI.
 * @integration-point VALIDATION_SERVICE
 */
export const validationService = {
  async runValidation(payload: ValidationRunRequest): Promise<ValidationRunResponse> {
    return apiRequest<ValidationRunResponse>('/validation/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getRunHistory(): Promise<unknown[]> {
    // @integration-point VALIDATION_HISTORY
    return [];
  },

  async getFindings(_runId: string): Promise<unknown[]> {
    // @integration-point VALIDATION_FINDINGS
    return [];
  },
};
