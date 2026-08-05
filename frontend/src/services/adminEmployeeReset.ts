import { apiRequest } from './api';

export const RESET_EMPLOYEE_DATA_PHRASE = 'RESET_EMPLOYEE_DATA';

export type ResetEmployeeDataCounts = {
  employees: number;
  employee_user_bindings: number;
  documents: number;
  extractions: number;
  validation_runs: number;
  validation_findings: number;
  vacations: number;
  sick_leaves: number;
  leave_idempotency: number;
  s3_objects: number;
  s3_orphan_prefix_objects: number;
  redis_manual_review_items: number;
  redis_batch_progress_jobs: number;
  redis_guest_session_keys: number;
  organization_id: string;
};

export type ResetEmployeeDataResult = {
  organization_id: string;
  confirmation_phrase_required: string;
  idempotent: boolean;
  counts: ResetEmployeeDataCounts;
};

export const adminEmployeeResetService = {
  async resetEmployeeData(input: {
    confirmationPhrase: string;
    confirmDestruction: boolean;
  }): Promise<ResetEmployeeDataResult> {
    return apiRequest<ResetEmployeeDataResult>('/admin/reset-employee-data', {
      method: 'POST',
      portalAuth: true,
      body: JSON.stringify({
        confirmation_phrase: input.confirmationPhrase,
        confirm_destruction: input.confirmDestruction,
      }),
    });
  },
};
