import { ApiClientError } from '../services/api';

/** True when the browser reports a network-level fetch failure (not an HTTP error body). */
export function isNetworkFetchError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const message = err.message.trim().toLowerCase();
  return (
    message === 'failed to fetch' ||
    message === 'networkerror when attempting to fetch resource.' ||
    message === 'network request failed' ||
    message === 'load failed' ||
    message.includes('failed to fetch')
  );
}

/**
 * Normalize thrown values for UI error strings without changing API clients.
 * Prefer `networkFallback` (i18n) over raw English "Failed to fetch".
 */
export function getDisplayError(
  err: unknown,
  fallback: string,
  options?: { networkFallback?: string },
): string {
  if (options?.networkFallback && isNetworkFetchError(err)) {
    return options.networkFallback;
  }
  if (err instanceof ApiClientError || err instanceof Error) {
    const message = err.message?.trim();
    if (message) {
      if (options?.networkFallback && /failed to fetch/i.test(message)) {
        return options.networkFallback;
      }
      return message;
    }
  }
  if (typeof err === 'string' && err.trim()) {
    if (options?.networkFallback && /failed to fetch/i.test(err)) {
      return options.networkFallback;
    }
    return err.trim();
  }
  return fallback;
}
