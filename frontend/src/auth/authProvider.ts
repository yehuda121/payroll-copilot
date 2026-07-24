/**
 * Amazon Cognito auth provider (via backend /auth/login + /auth/refresh).
 * Keeps Cognito secrets and USER_PASSWORD_AUTH on the server.
 *
 * Token storage:
 * - Access token: sessionStorage only (see access-token.ts)
 * - Refresh token: sessionStorage (tab-scoped; not persisted in localStorage)
 * - Session metadata (user/role): localStorage for UX bootstrap only — not used for authorization
 */

import type { AuthSession, AuthUser, LoginCredentials, UserRole } from '../types/auth';
import { apiRequest } from '../services/api';
import { clearAccessToken, loadAccessToken, saveAccessToken } from '../lib/auth/access-token';

export type AuthProvider = {
  login(credentials: LoginCredentials): Promise<AuthSession>;
  logout(): Promise<void>;
  getSession(): AuthSession | null;
  refreshSession(): Promise<AuthSession | null>;
};

const SESSION_KEY = 'payroll_copilot_cognito_session';
const REFRESH_KEY = 'payroll_copilot_refresh_token';
const LEGACY_REFRESH_KEY = REFRESH_KEY;

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    role: string;
    preferred_locale?: string;
    organization_id?: string | null;
    employee_id?: string | null;
    full_name?: string;
  };
};

type PersistedCognitoSession = Omit<AuthSession, 'accessToken'>;

function isUserRole(value: string): value is UserRole {
  return value === 'employee' || value === 'payroll_accountant' || value === 'developer_admin';
}

function mapUser(payload: TokenResponse['user']): AuthUser {
  const role = isUserRole(payload.role) ? payload.role : 'employee';
  return {
    id: payload.id,
    email: payload.email,
    fullName: payload.full_name || payload.email,
    role,
    organizationId: payload.organization_id || '',
  };
}

function toSession(response: TokenResponse): AuthSession {
  return {
    user: mapUser(response.user),
    provider: 'cognito',
    issuedAt: new Date().toISOString(),
    accessToken: response.access_token,
  };
}

function loadRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY) ?? localStorage.getItem(LEGACY_REFRESH_KEY);
}

function saveRefreshToken(token: string | null): void {
  localStorage.removeItem(LEGACY_REFRESH_KEY);
  if (!token) {
    sessionStorage.removeItem(REFRESH_KEY);
    return;
  }
  sessionStorage.setItem(REFRESH_KEY, token);
}

function persistSession(session: AuthSession, refreshToken?: string): void {
  const { accessToken: _accessToken, ...rest } = session;
  localStorage.setItem(SESSION_KEY, JSON.stringify(rest satisfies PersistedCognitoSession));
  if (refreshToken) {
    saveRefreshToken(refreshToken);
  }
  if (session.accessToken) {
    saveAccessToken(session.accessToken);
  }
}

export function loadCognitoSession(): AuthSession | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PersistedCognitoSession;
    if (parsed?.provider !== 'cognito' || !parsed.user) return null;
    const token = loadAccessToken();
    return token ? { ...parsed, accessToken: token } : null;
  } catch {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function clearCognitoSession(): void {
  localStorage.removeItem(SESSION_KEY);
  saveRefreshToken(null);
  clearAccessToken();
}

/** Route prefix per role after authentication. */
export function getRoleHomePath(role: UserRole): string {
  switch (role) {
    case 'employee':
      return '/employee/chat';
    case 'payroll_accountant':
      return '/accountant/employees';
    case 'developer_admin':
      return '/admin';
  }
}

export function isRoleAllowed(user: AuthUser, allowedRoles: UserRole[]): boolean {
  return allowedRoles.includes(user.role);
}

/**
 * Production Cognito provider — authenticates through the API (Cognito User Pool).
 */
export const cognitoAuthProvider: AuthProvider = {
  async login(credentials: LoginCredentials): Promise<AuthSession> {
    const response = await apiRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: credentials.email,
        password: credentials.password,
      }),
    });
    const session = toSession(response);
    persistSession(session, response.refresh_token);
    return session;
  },

  async logout(): Promise<void> {
    clearCognitoSession();
  },

  getSession(): AuthSession | null {
    return loadCognitoSession();
  },

  async refreshSession(): Promise<AuthSession | null> {
    const refreshToken = loadRefreshToken();
    const current = loadCognitoSession();
    if (!refreshToken) return null;
    try {
      const response = await apiRequest<TokenResponse>('/auth/refresh', {
        method: 'POST',
        skipPortalAuthRefresh: true,
        body: JSON.stringify({
          refresh_token: refreshToken,
          username: current?.user.email,
        }),
      });
      const session = toSession(response);
      persistSession(session, response.refresh_token || refreshToken);
      return session;
    } catch {
      clearCognitoSession();
      return null;
    }
  },
};
