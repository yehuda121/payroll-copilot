import type {
  DocumentLanguage,
  DynamicDocumentEntry,
  GuestExtractionCorrectionRequest,
  GuestPayslipExtractionResponse,
} from '../types';
import { apiRequest } from './api';

export const extractionService = {
  async extractGuestPayslip(
    file: File,
    language: DocumentLanguage = 'auto',
    signal?: AbortSignal,
  ): Promise<GuestPayslipExtractionResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('language', language);

    return apiRequest<GuestPayslipExtractionResponse>('/extraction/guest/payslip-extract', {
      method: 'POST',
      body: formData,
      rawBody: true,
      auth: true,
      signal,
    });
  },

  async confirmGuestExtraction(
    documentId: string,
    entries?: DynamicDocumentEntry[],
  ): Promise<{ document_id: string; extraction_id: string; status: string }> {
    return apiRequest(`/extraction/guest/${documentId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(entries ? { entries } : {}),
      auth: true,
    });
  },

  async uploadGuestSupporting(
    file: File,
    documentType: 'national_id' | 'contract',
    payslipDocumentId?: string,
    signal?: AbortSignal,
  ): Promise<{ document_id: string; document_type: string; status: string }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    if (payslipDocumentId) {
      formData.append('payslip_document_id', payslipDocumentId);
    }
    return apiRequest('/extraction/guest/supporting-upload', {
      method: 'POST',
      body: formData,
      rawBody: true,
      auth: true,
      signal,
    });
  },

  async correctGuestExtraction(
    documentId: string,
    payload: GuestExtractionCorrectionRequest,
  ): Promise<GuestPayslipExtractionResponse> {
    return apiRequest<GuestPayslipExtractionResponse>(
      `/extraction/guest/${documentId}/corrections`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
        auth: true,
      },
    );
  },
};
