import { apiRequest } from './api';
import type { DocumentLanguage, ExtractedPayslipField, ValidationRunResponse } from '../types';

export type ComparisonField = {
  key: string;
  status: string;
  extracted_display: string | null;
  expected_display: string | null;
  severity: string;
  blocks_confirmation: boolean;
  explanation_code: string | null;
};

export type IdentityCheck = {
  overall: string;
  blocks_confirmation: boolean;
  fields: ComparisonField[];
};

export type PeriodCheck = {
  status: string;
  blocks_confirmation: boolean;
  selected_year: number;
  selected_month: number;
  extracted_year: number | null;
  extracted_month: number | null;
  explanation_code: string | null;
};

export type EmployeePayslipExtraction = {
  document_id: string;
  extraction_id: string;
  extraction_version?: number | null;
  ocr_status: string;
  parser_status: string;
  language: string;
  warnings: string[];
  fields: ExtractedPayslipField[];
  error_message?: string | null;
  identity_check: IdentityCheck;
  period_check: PeriodCheck;
  blocks_confirmation: boolean;
  document_version?: number | null;
};

export type EmployeeMe = {
  employee_id: string;
  employee_number: string;
  full_name: string;
  national_id_masked: string | null;
  organization_id: string;
  status: string;
  profile_incomplete: boolean;
};

export type EmployeePayslipListItem = {
  document_id: string;
  original_filename: string;
  status: string;
  period_year: number | null;
  period_month: number | null;
  extracted_period_year: number | null;
  extracted_period_month: number | null;
  uploaded_at: string | null;
  manual_corrections: boolean;
};

export const employeePortalService = {
  async me(): Promise<EmployeeMe> {
    return apiRequest<EmployeeMe>('/employees/me', { portalAuth: true });
  },

  async listMyPayslips(year?: number): Promise<EmployeePayslipListItem[]> {
    const suffix = year != null ? `?year=${year}` : '';
    return apiRequest<EmployeePayslipListItem[]>(`/employees/me/payslips${suffix}`, {
      portalAuth: true,
    });
  },

  async extractPayslip(
    file: File,
    options: {
      language?: DocumentLanguage;
      periodYear: number;
      periodMonth: number;
      confirmNewVersion?: boolean;
    },
  ): Promise<EmployeePayslipExtraction> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('language', options.language ?? 'auto');
    formData.append('period_year', String(options.periodYear));
    formData.append('period_month', String(options.periodMonth));
    formData.append('confirm_new_version', options.confirmNewVersion ? 'true' : 'false');
    return apiRequest<EmployeePayslipExtraction>('/extraction/employee/payslip-extract', {
      method: 'POST',
      body: formData,
      rawBody: true,
      portalAuth: true,
    });
  },

  async correctExtraction(
    documentId: string,
    corrections: Array<{ key: string; value?: unknown; clear?: boolean }>,
  ): Promise<EmployeePayslipExtraction> {
    return apiRequest<EmployeePayslipExtraction>(
      `/extraction/employee/${encodeURIComponent(documentId)}/corrections`,
      {
        method: 'POST',
        body: JSON.stringify({ corrections }),
        portalAuth: true,
      },
    );
  },

  async validatePayslip(input: {
    documentId: string;
    locale?: string;
    supportingDocumentIds?: string[];
  }): Promise<ValidationRunResponse> {
    return apiRequest<ValidationRunResponse>('/validation/employee/run', {
      method: 'POST',
      body: JSON.stringify({
        document_id: input.documentId,
        supporting_document_ids: input.supportingDocumentIds ?? [],
        locale: input.locale,
      }),
      portalAuth: true,
    });
  },
};
