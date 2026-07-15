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
  full_name_localized?: string | null;
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

export type PayrollMonthDocSummary = {
  exists: boolean;
  document_id: string | null;
  uploaded_at: string | null;
  status: string;
  original_filename?: string | null;
  analysis_status?: string;
};

export type PayrollMonthValidationSummary = {
  exists: boolean;
  validation_run_id: string | null;
  status: string;
  overall_result?: string | null;
  confidence: number | null;
  completed_at: string | null;
  findings_count: number;
  highest_severity: string | null;
  scope: Array<{ key: string; label: string; status: string; reason?: string | null }>;
  findings?: Array<{
    id: string;
    code: string;
    severity: string;
    message_key: string;
    expected_value?: string | null;
    actual_value?: string | null;
    confidence?: number | null;
    legal_reference?: string | null;
  }>;
};

export type PayrollMonthSummary = {
  month: number;
  payslip: PayrollMonthDocSummary;
  attendance: PayrollMonthDocSummary;
  latest_validation: PayrollMonthValidationSummary;
  presentation_status: string;
};

export type PayrollMonthsResponse = {
  year: number;
  available_years: number[];
  months: PayrollMonthSummary[];
};

export type PayrollMonthDetail = {
  year: number;
  month: number;
  payslip: PayrollMonthDocSummary;
  attendance: PayrollMonthDocSummary;
  extraction?: {
    exists: boolean;
    extraction_id: string | null;
    extraction_version: number | null;
    confirmation_status: string;
    lifecycle_status: string;
    original_filename?: string | null;
    fields: Array<Record<string, unknown>>;
  };
  validation_history?: Array<{
    validation_run_id: string;
    status: string;
    overall_result: string | null;
    confidence: number | null;
    completed_at: string | null;
    extraction_id: string | null;
    outdated: boolean;
  }>;
  latest_validation: PayrollMonthValidationSummary & {
    outdated?: boolean;
    extraction_id?: string | null;
  };
  missing_documents: Array<{ document_type: string; reason_code: string }>;
  presentation_status: string;
  actions: {
    can_upload_payslip: boolean;
    can_upload_attendance: boolean;
    can_run_validation: boolean;
    can_confirm_extraction?: boolean;
    can_review_extraction?: boolean;
  };
};

export type EmployeeDocumentCenterItem = {
  document_type: string;
  exists: boolean;
  document_id: string | null;
  original_filename: string | null;
  uploaded_at: string | null;
  processing_status: string;
  extraction_status: string;
  confirmation_status: string;
  lifecycle_status: string;
  extraction_connection: string;
  version_count: number;
  payroll_year: number | null;
  payroll_month: number | null;
  actions: {
    can_upload: boolean;
    can_replace: boolean;
    can_review: boolean;
    can_confirm: boolean;
  };
};

export type EmployeeDocumentCenter = {
  persistent_documents: EmployeeDocumentCenterItem[];
  monthly_documents: {
    count: number;
    access_path: string;
    note_code: string;
  };
  national_id_review: {
    extraction_connection: string;
    parser_status: string;
  };
};

export type FindingExplanation = {
  finding_id: string;
  validation_status: string;
  explanation_status: string;
  explanation: string | null;
  recommended_action: string | null;
  sources: Array<{ source_type?: string; source_id?: string; title?: string | null }>;
  disclaimer_key: string;
};

export const employeePortalService = {
  async me(): Promise<EmployeeMe> {
    return apiRequest<EmployeeMe>('/employees/me', { portalAuth: true });
  },

  async listDocuments(): Promise<EmployeeDocumentCenter> {
    return apiRequest<EmployeeDocumentCenter>('/employees/me/documents', { portalAuth: true });
  },

  async getNationalIdReview(): Promise<Record<string, unknown>> {
    return apiRequest('/employees/me/documents/national-id/review', { portalAuth: true });
  },

  async explainFinding(
    validationRunId: string,
    findingId: string,
    locale?: string,
  ): Promise<FindingExplanation> {
    const q = locale ? `?locale=${encodeURIComponent(locale)}` : '';
    return apiRequest<FindingExplanation>(
      `/employees/me/validation-runs/${encodeURIComponent(validationRunId)}/findings/${encodeURIComponent(findingId)}/explanation${q}`,
      { method: 'POST', portalAuth: true },
    );
  },

  async listMyPayslips(year?: number): Promise<EmployeePayslipListItem[]> {
    const suffix = year != null ? `?year=${year}` : '';
    return apiRequest<EmployeePayslipListItem[]>(`/employees/me/payslips${suffix}`, {
      portalAuth: true,
    });
  },

  async listPayrollMonths(year?: number): Promise<PayrollMonthsResponse> {
    const suffix = year != null ? `?year=${year}` : '';
    return apiRequest<PayrollMonthsResponse>(`/employees/me/payroll-months${suffix}`, {
      portalAuth: true,
    });
  },

  async getPayrollMonthDetail(year: number, month: number): Promise<PayrollMonthDetail> {
    return apiRequest<PayrollMonthDetail>(
      `/employees/me/payroll-months/${year}/${month}`,
      { portalAuth: true },
    );
  },

  async uploadOwnedDocument(
    file: File,
    options: {
      documentType: 'attendance' | 'contract' | 'national_id' | 'id_appendix';
      periodYear?: number;
      periodMonth?: number;
      language?: DocumentLanguage;
    },
  ): Promise<{ document_id: string; status: string }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', options.documentType);
    if (options.periodYear != null) {
      formData.append('period_year', String(options.periodYear));
    }
    if (options.periodMonth != null) {
      formData.append('period_month', String(options.periodMonth));
    }
    formData.append('document_language', options.language ?? 'auto');
    return apiRequest('/documents/employee/upload', {
      method: 'POST',
      body: formData,
      rawBody: true,
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

  async confirmExtraction(
    documentId: string,
    acknowledgement: boolean,
  ): Promise<{ confirmation_status: string; extraction_id: string }> {
    return apiRequest(`/extraction/employee/${encodeURIComponent(documentId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ acknowledgement }),
      portalAuth: true,
    });
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
