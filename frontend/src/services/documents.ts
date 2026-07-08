import type { DocumentLanguage, DocumentUploadResponse, DocumentResponse } from '../types';
import { apiRequest } from './api';
import type { GuestDocumentSlot } from '../lib/guest/document-slots';

export type BackendDocumentType = GuestDocumentSlot['backendType'];

export const documentsService = {
  async upload(
    file: File,
    documentType: BackendDocumentType,
    documentLanguage: DocumentLanguage = 'auto',
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    formData.append('document_language', documentLanguage);

    return apiRequest<DocumentUploadResponse>('/documents/upload', {
      method: 'POST',
      body: formData,
      rawBody: true,
      auth: true,
    });
  },

  async getDocument(documentId: string): Promise<DocumentResponse> {
    return apiRequest<DocumentResponse>(`/documents/${documentId}`, { auth: true });
  },
};
