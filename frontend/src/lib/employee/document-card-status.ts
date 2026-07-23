export type DocumentCardStatus = 'loading' | 'missing' | 'needs_review' | 'verified';

export function resolveDocumentCardStatus(input: {
  loading: boolean;
  settled: boolean;
  hasOriginal: boolean;
  hasDigital: boolean;
  confirmationStatus?: string | null;
}): DocumentCardStatus {
  if (input.loading || !input.settled) return 'loading';
  if (!input.hasOriginal && !input.hasDigital) return 'missing';
  if (input.confirmationStatus === 'confirmed') return 'verified';
  return 'needs_review';
}
