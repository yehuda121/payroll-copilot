import type { DocumentLanguage, DocumentUploadResponse, DocumentResponse } from '../types';
import { apiRequest } from './api';
import type { GuestDocumentSlot } from '../lib/guest/document-slots';

export type BackendDocumentType = GuestDocumentSlot['backendType'] | string;

export type DocumentUploadOptions = {
  employeeId?: string;
  periodYear?: number;
  periodMonth?: number;
};

export const documentsService = {
  async upload(
    file: File,
    documentType: BackendDocumentType,
    documentLanguage: DocumentLanguage = 'auto',
    options?: DocumentUploadOptions,
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    formData.append('document_language', documentLanguage);
    if (options?.employeeId) {
      formData.append('employee_id', options.employeeId);
    }
    if (options?.periodYear != null) {
      formData.append('period_year', String(options.periodYear));
    }
    if (options?.periodMonth != null) {
      formData.append('period_month', String(options.periodMonth));
    }

    return apiRequest<DocumentUploadResponse>('/documents/upload', {
      method: 'POST',
      body: formData,
      rawBody: true,
      portalAuth: true,
    });
  },

  async getDocument(documentId: string): Promise<DocumentResponse> {
    return apiRequest<DocumentResponse>(`/documents/${documentId}`, { portalAuth: true });
  },
};
