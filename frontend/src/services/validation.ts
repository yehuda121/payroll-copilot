import type { ValidationRunRequest, ValidationRunResponse } from '../types';
import { apiRequest } from './api';

export const validationService = {
  async runValidation(payload: ValidationRunRequest): Promise<ValidationRunResponse> {
    return apiRequest<ValidationRunResponse>('/validation/run', {
      method: 'POST',
      body: JSON.stringify(payload),
      auth: true,
    });
  },

  async getValidationRun(validationRunId: string): Promise<ValidationRunResponse> {
    return apiRequest<ValidationRunResponse>(`/validation/runs/${validationRunId}`, {
      auth: true,
    });
  },
};
