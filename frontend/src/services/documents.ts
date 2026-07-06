import type { DocumentUploadResponse } from '../types';
import { apiRequest } from './api';

export type DocumentType = 'payslip' | 'attendance' | 'contract' | 'id_document';

/**
 * Document upload and retrieval.
 * @integration-point DOCUMENTS_SERVICE
 */
export const documentsService = {
  async upload(file: File, documentType: DocumentType): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    return apiRequest<DocumentUploadResponse>('/documents/upload', {
      method: 'POST',
      body: formData,
      rawBody: true,
    });
  },

  async listMyDocuments(): Promise<unknown[]> {
    // @integration-point DOCUMENTS_LIST
    return [];
  },
};
