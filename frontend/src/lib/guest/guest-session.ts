const GUEST_TOKEN_KEY = 'payroll_copilot_guest_token';
const GUEST_EXPIRES_KEY = 'payroll_copilot_guest_expires_at';

export function getGuestToken(): string | null {
  const token = sessionStorage.getItem(GUEST_TOKEN_KEY);
  const expiresAt = sessionStorage.getItem(GUEST_EXPIRES_KEY);
  if (!token || !expiresAt) {
    return null;
  }
  if (new Date(expiresAt).getTime() <= Date.now()) {
    clearGuestSession();
    return null;
  }
  return token;
}

export function setGuestSession(token: string, expiresAt: string): void {
  sessionStorage.setItem(GUEST_TOKEN_KEY, token);
  sessionStorage.setItem(GUEST_EXPIRES_KEY, expiresAt);
}

export function clearGuestSession(): void {
  sessionStorage.removeItem(GUEST_TOKEN_KEY);
  sessionStorage.removeItem(GUEST_EXPIRES_KEY);
}

export function getAuthHeaders(): HeadersInit {
  const token = getGuestToken();
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}
