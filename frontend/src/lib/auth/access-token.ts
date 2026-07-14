/**
 * Session access-token helpers for authenticated portal API calls.
 * Guest tokens remain separate (guest-session.ts).
 */

import { loadDevSession } from '../../auth/devAuth';

const ACCESS_TOKEN_KEY = 'payroll_copilot_access_token';

export function saveAccessToken(token: string | null): void {
  if (!token) {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    return;
  }
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function loadAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

/** Prefer stored access token; fall back to persisted session.accessToken. */
export function getPortalAuthHeaders(): Record<string, string> {
  const token = loadAccessToken() ?? loadDevSession()?.accessToken ?? null;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
