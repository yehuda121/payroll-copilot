import { describe, expect, it } from 'vitest';
import { resolveDocumentCardStatus } from './document-card-status';

describe('resolveDocumentCardStatus', () => {
  it('returns loading until settled', () => {
    expect(
      resolveDocumentCardStatus({
        loading: true,
        settled: false,
        hasOriginal: false,
        hasDigital: false,
      }),
    ).toBe('loading');
  });

  it('never returns missing before settled', () => {
    expect(
      resolveDocumentCardStatus({
        loading: false,
        settled: false,
        hasOriginal: false,
        hasDigital: false,
      }),
    ).toBe('loading');
  });

  it('returns missing only when settled and empty', () => {
    expect(
      resolveDocumentCardStatus({
        loading: false,
        settled: true,
        hasOriginal: false,
        hasDigital: false,
      }),
    ).toBe('missing');
  });

  it('returns verified when confirmed', () => {
    expect(
      resolveDocumentCardStatus({
        loading: false,
        settled: true,
        hasOriginal: true,
        hasDigital: true,
        confirmationStatus: 'confirmed',
      }),
    ).toBe('verified');
  });

  it('returns needs_review otherwise', () => {
    expect(
      resolveDocumentCardStatus({
        loading: false,
        settled: true,
        hasOriginal: true,
        hasDigital: false,
        confirmationStatus: 'review_required',
      }),
    ).toBe('needs_review');
  });
});
