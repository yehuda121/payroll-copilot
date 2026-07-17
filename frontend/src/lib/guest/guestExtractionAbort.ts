/** Guest extraction abort / error-mapping helpers (pure, unit-testable). */

export function isAbortError(err: unknown): boolean {
  if (err == null || typeof err !== 'object') return false;
  const name = 'name' in err ? String((err as { name?: unknown }).name) : '';
  if (name === 'AbortError' || name === 'CanceledError') return true;
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  return false;
}

/**
 * Map an extraction failure to a user-facing message.
 * Only intentional AbortError becomes "Extraction cancelled."
 * Backend failures keep their original message.
 */
export function mapExtractionFailureMessage(
  err: unknown,
  options: {
    intentionallyCancelled: boolean;
    cancelledMessage: string;
    fallbackMessage: string;
  },
): string {
  if (options.intentionallyCancelled && isAbortError(err)) {
    return options.cancelledMessage;
  }
  if (err instanceof Error && err.message.trim()) {
    return err.message;
  }
  return options.fallbackMessage;
}

/**
 * One Send → one AbortController. Abort only on explicit cancel / reset / unmount.
 * Starting a new Send while busy is rejected (no auto-abort of the in-flight request).
 */
export class GuestExtractionSubmission {
  private controller: AbortController | null = null;
  private intentional = false;
  private busy = false;

  get signal(): AbortSignal | null {
    return this.controller?.signal ?? null;
  }

  get isBusy(): boolean {
    return this.busy;
  }

  get wasIntentionallyCancelled(): boolean {
    return this.intentional;
  }

  /** Begin a submission. Returns null if already busy (does not abort). */
  begin(): AbortSignal | null {
    if (this.busy) return null;
    this.intentional = false;
    this.controller = new AbortController();
    this.busy = true;
    return this.controller.signal;
  }

  /** Explicit user cancel, unmount, or session reset. */
  cancel(): void {
    if (!this.controller) return;
    this.intentional = true;
    this.controller.abort();
    this.controller = null;
    this.busy = false;
  }

  /** Clear pending attachment chips / re-render — must not abort. */
  onPendingCleared(): void {
    // no-op by design
  }

  /** Re-render — must not abort. */
  onRerender(): void {
    // no-op by design
  }

  end(): void {
    this.busy = false;
    this.controller = null;
  }
}
