import type {
  DocumentLanguage,
  GuestExtractionCorrectionRequest,
  GuestPayslipExtractionResponse,
} from '../types';
import { apiRequest } from './api';

export const extractionService = {
  async extractGuestPayslip(
    file: File,
    language: DocumentLanguage = 'auto',
  ): Promise<GuestPayslipExtractionResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('language', language);

    return apiRequest<GuestPayslipExtractionResponse>('/extraction/guest/payslip-extract', {
      method: 'POST',
      body: formData,
      rawBody: true,
      auth: true,
    });
  },

  async correctGuestExtraction(
    documentId: string,
    corrections: GuestExtractionCorrectionRequest['corrections'],
  ): Promise<GuestPayslipExtractionResponse> {
    return apiRequest<GuestPayslipExtractionResponse>(
      `/extraction/guest/${documentId}/corrections`,
      {
        method: 'POST',
        body: JSON.stringify({ corrections }),
        auth: true,
      },
    );
  },
};
