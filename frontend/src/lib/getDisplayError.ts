import { ApiClientError } from '../services/api';

/** Normalize thrown values for UI error strings without changing API clients. */
export function getDisplayError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError || err instanceof Error) {
    const message = err.message?.trim();
    if (message) return message;
  }
  if (typeof err === 'string' && err.trim()) return err.trim();
  return fallback;
}
