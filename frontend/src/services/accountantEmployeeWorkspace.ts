import { getPortalAuthHeaders } from '../lib/auth/access-token';
import type { DocumentLanguage, ValidationRunResponse } from '../types/api';
import { env } from '../config/env';
import { apiRequest } from './api';
import {
  employeePortalService,
  type EmployeeDocumentCenter,
  type EmployeeDocumentForm,
  type EmployeeMe,
  type EmployeePayslipExtraction,
  type FindingExplanation,
  type PayrollMonthDetail,
  type PayrollMonthsResponse,
} from './employeePortal';

function selectedBase(employeeNumber: string): string {
  return `/employees/${encodeURIComponent(employeeNumber)}/workspace`;
}

function extractionBase(employeeNumber: string): string {
  return `/extraction/accountant/${encodeURIComponent(employeeNumber)}`;
}

function documentBase(employeeNumber: string): string {
  return `/documents/accountant/${encodeURIComponent(employeeNumber)}`;
}

/**
 * Same frontend workspace contract as Employee Portal, backed by accountant
 * endpoints that resolve `employeeNumber` inside the authenticated organization.
 */
export function createAccountantEmployeeWorkspaceApi(
  employeeNumber: string,
  reviewDocumentId?: string,
): typeof employeePortalService {
  const employeePath = selectedBase(employeeNumber);
  const extractionPath = extractionBase(employeeNumber);
  const documentsPath = documentBase(employeeNumber);

  return {
    ...employeePortalService,

    async me(): Promise<EmployeeMe> {
      return apiRequest<EmployeeMe>(`${employeePath}/me`, { portalAuth: true });
    },

    async listDocuments(): Promise<EmployeeDocumentCenter> {
      return apiRequest<EmployeeDocumentCenter>(`${employeePath}/documents`, {
        portalAuth: true,
      });
    },

    async explainFinding(
      validationRunId: string,
      findingId: string,
      locale?: string,
    ): Promise<FindingExplanation> {
      const query = locale ? `?locale=${encodeURIComponent(locale)}` : '';
      return apiRequest<FindingExplanation>(
        `${employeePath}/validation-runs/${encodeURIComponent(validationRunId)}/findings/${encodeURIComponent(findingId)}/explanation${query}`,
        { method: 'POST', portalAuth: true },
      );
    },

    async listPayrollMonths(year?: number): Promise<PayrollMonthsResponse> {
      const query = year == null ? '' : `?year=${year}`;
      return apiRequest<PayrollMonthsResponse>(`${employeePath}/payroll-months${query}`, {
        portalAuth: true,
      });
    },

    async getPayrollMonthDetail(year: number, month: number): Promise<PayrollMonthDetail> {
      const query = reviewDocumentId
        ? `?document_id=${encodeURIComponent(reviewDocumentId)}`
        : '';
      return apiRequest<PayrollMonthDetail>(
        `${employeePath}/payroll-months/${year}/${month}${query}`,
        { portalAuth: true },
      );
    },

    async uploadOwnedDocument(
      file: File,
      options: {
        documentType: 'attendance' | 'contract' | 'national_id' | 'id_appendix' | 'payslip';
        periodYear?: number;
        periodMonth?: number;
        language?: DocumentLanguage;
        signal?: AbortSignal;
      },
    ): Promise<{ document_id: string; status: string }> {
      const body = new FormData();
      body.append('file', file);
      body.append('document_type', options.documentType);
      if (options.periodYear != null) body.append('period_year', String(options.periodYear));
      if (options.periodMonth != null) body.append('period_month', String(options.periodMonth));
      body.append('document_language', options.language ?? 'auto');
      return apiRequest(`${documentsPath}/upload`, {
        method: 'POST',
        body,
        rawBody: true,
        portalAuth: true,
        signal: options.signal,
      });
    },

    async extractEmployeeDocument(
      file: File,
      options: {
        documentType: 'national_id' | 'id_appendix' | 'contract';
        language?: DocumentLanguage;
        signal?: AbortSignal;
      },
    ): Promise<EmployeeDocumentForm> {
      const body = new FormData();
      body.append('file', file);
      body.append('document_type', options.documentType);
      body.append('language', options.language ?? 'auto');
      return apiRequest<EmployeeDocumentForm>(`${extractionPath}/document-extract`, {
        method: 'POST',
        body,
        rawBody: true,
        portalAuth: true,
        signal: options.signal,
      });
    },

    async getEmployeeDocumentForm(documentId: string): Promise<EmployeeDocumentForm> {
      return apiRequest<EmployeeDocumentForm>(
        `${extractionPath}/document/${encodeURIComponent(documentId)}`,
        { portalAuth: true },
      );
    },

    async saveEmployeeDocumentForm(documentId, fields): Promise<EmployeeDocumentForm> {
      return apiRequest<EmployeeDocumentForm>(
        `${extractionPath}/document/${encodeURIComponent(documentId)}`,
        { method: 'PUT', body: JSON.stringify({ fields }), portalAuth: true },
      );
    },

    async saveEmployeeDocumentFormByType(documentType, fields): Promise<EmployeeDocumentForm> {
      return apiRequest<EmployeeDocumentForm>(
        `${extractionPath}/document-type/${encodeURIComponent(documentType)}`,
        { method: 'PUT', body: JSON.stringify({ fields }), portalAuth: true },
      );
    },

    async extractPayslip(file, options): Promise<EmployeePayslipExtraction> {
      const body = new FormData();
      if (file) body.append('file', file);
      if (options.documentId) body.append('document_id', options.documentId);
      body.append('language', options.language ?? 'auto');
      body.append('period_year', String(options.periodYear));
      body.append('period_month', String(options.periodMonth));
      body.append('confirm_new_version', options.confirmNewVersion ? 'true' : 'false');
      return apiRequest<EmployeePayslipExtraction>(`${extractionPath}/payslip-extract`, {
        method: 'POST',
        body,
        rawBody: true,
        portalAuth: true,
        signal: options.signal,
      });
    },

    async resolvePayslipPeriod(documentId, action) {
      return apiRequest(
        `${documentsPath}/${encodeURIComponent(documentId)}/resolve-period`,
        { method: 'POST', body: JSON.stringify({ action }), portalAuth: true },
      );
    },

    async fetchDocumentContentBlob(documentId: string, signal?: AbortSignal): Promise<Blob> {
      const response = await fetch(
        `${env.apiBaseUrl}${documentsPath}/${encodeURIComponent(documentId)}/content`,
        { headers: getPortalAuthHeaders(), signal },
      );
      if (!response.ok) {
        throw new Error(`Failed to load document content (${response.status})`);
      }
      return response.blob();
    },

    async deleteOwnedDocument(documentId: string) {
      return apiRequest(`${documentsPath}/${encodeURIComponent(documentId)}`, {
        method: 'DELETE',
        portalAuth: true,
      });
    },

    async correctExtraction(documentId, corrections): Promise<EmployeePayslipExtraction> {
      return apiRequest<EmployeePayslipExtraction>(
        `${extractionPath}/${encodeURIComponent(documentId)}/corrections`,
        {
          method: 'POST',
          body: JSON.stringify({ corrections }),
          portalAuth: true,
        },
      );
    },

    async confirmExtraction(documentId, acknowledgement) {
      return apiRequest(`${extractionPath}/${encodeURIComponent(documentId)}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ acknowledgement }),
        portalAuth: true,
      });
    },

    async validatePayslip(input): Promise<ValidationRunResponse> {
      return apiRequest<ValidationRunResponse>(
        `/validation/accountant/${encodeURIComponent(employeeNumber)}/run`,
        {
          method: 'POST',
          body: JSON.stringify({
            document_id: input.documentId,
            supporting_document_ids: input.supportingDocumentIds ?? [],
            locale: input.locale,
          }),
          portalAuth: true,
          signal: input.signal,
        },
      );
    },
  };
}
