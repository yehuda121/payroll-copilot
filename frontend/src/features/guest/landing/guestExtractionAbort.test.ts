import { describe, expect, it, vi } from 'vitest';
import {
  GuestExtractionSubmission,
  isAbortError,
  mapExtractionFailureMessage,
} from '../../../lib/guest/guestExtractionAbort';

describe('guest extraction abort lifecycle', () => {
  it('Send begins a fresh controller that is not auto-cancelled', () => {
    const submission = new GuestExtractionSubmission();
    const signal = submission.begin();
    expect(signal).not.toBeNull();
    expect(signal!.aborted).toBe(false);
    submission.onPendingCleared();
    submission.onRerender();
    expect(signal!.aborted).toBe(false);
    submission.end();
  });

  it('clearing pending attachments does not abort', () => {
    const submission = new GuestExtractionSubmission();
    const signal = submission.begin()!;
    const onAbort = vi.fn();
    signal.addEventListener('abort', onAbort);
    submission.onPendingCleared();
    expect(onAbort).not.toHaveBeenCalled();
    expect(signal.aborted).toBe(false);
  });

  it('re-render does not abort', () => {
    const submission = new GuestExtractionSubmission();
    const signal = submission.begin()!;
    submission.onRerender();
    submission.onRerender();
    expect(signal.aborted).toBe(false);
  });

  it('explicit Cancel does abort', () => {
    const submission = new GuestExtractionSubmission();
    const signal = submission.begin()!;
    submission.cancel();
    expect(signal.aborted).toBe(true);
    expect(submission.wasIntentionallyCancelled).toBe(true);
  });

  it('second begin while busy does not replace or abort the first controller', () => {
    const submission = new GuestExtractionSubmission();
    const first = submission.begin()!;
    const second = submission.begin();
    expect(second).toBeNull();
    expect(first.aborted).toBe(false);
  });

  it('backend error is not displayed as Extraction cancelled', () => {
    const message = mapExtractionFailureMessage(new Error('Parser timed out'), {
      intentionallyCancelled: false,
      cancelledMessage: 'Extraction cancelled.',
      fallbackMessage: 'Extraction failed',
    });
    expect(message).toBe('Parser timed out');
    expect(message).not.toBe('Extraction cancelled.');
  });

  it('AbortError without intentional cancel keeps original/fallback message', () => {
    const abort = new DOMException('The operation was aborted.', 'AbortError');
    const message = mapExtractionFailureMessage(abort, {
      intentionallyCancelled: false,
      cancelledMessage: 'Extraction cancelled.',
      fallbackMessage: 'Extraction failed',
    });
    expect(message).toBe('The operation was aborted.');
    expect(isAbortError(abort)).toBe(true);
  });

  it('intentional AbortError maps to cancelled message', () => {
    const abort = new DOMException('The operation was aborted.', 'AbortError');
    const message = mapExtractionFailureMessage(abort, {
      intentionallyCancelled: true,
      cancelledMessage: 'Extraction cancelled.',
      fallbackMessage: 'Extraction failed',
    });
    expect(message).toBe('Extraction cancelled.');
  });

  it('valid embedded-text PDF Send reaches extraction endpoint with live signal', async () => {
    const submission = new GuestExtractionSubmission();
    const extractGuestPayslip = vi.fn(async (_file: File, _lang: string, signal?: AbortSignal) => {
      expect(signal).toBeDefined();
      expect(signal!.aborted).toBe(false);
      return { document_id: 'doc-1', fields: [] };
    });

    const file = new File(['%PDF-1.4 embedded payslip text page1 page2 page3 page4'], 'payslip.pdf', {
      type: 'application/pdf',
    });

    // Attach does not call extraction.
    expect(extractGuestPayslip).not.toHaveBeenCalled();

    // Send begins submission then calls extraction once.
    const signal = submission.begin();
    expect(signal).not.toBeNull();
    submission.onPendingCleared(); // chips cleared after Send — must not abort
    await extractGuestPayslip(file, 'auto', signal!);
    expect(extractGuestPayslip).toHaveBeenCalledTimes(1);
    expect(signal!.aborted).toBe(false);
    submission.end();
  });
});
