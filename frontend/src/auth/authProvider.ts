/**
 * Production auth boundary.
 * Replace dev auth with Cognito integration here — do not scatter auth logic across the app.
 */

import type { AuthSession, AuthUser, LoginCredentials, UserRole } from '../types/auth';

export type AuthProvider = {
  login(credentials: LoginCredentials): Promise<AuthSession>;
  logout(): Promise<void>;
  getSession(): AuthSession | null;
  refreshSession(): Promise<AuthSession | null>;
};

/** Route prefix per role after authentication. */
export function getRoleHomePath(role: UserRole): string {
  switch (role) {
    case 'employee':
      return '/employee';
    case 'payroll_accountant':
      return '/accountant';
    case 'developer_admin':
      return '/admin';
  }
}

export function isRoleAllowed(user: AuthUser, allowedRoles: UserRole[]): boolean {
  return allowedRoles.includes(user.role);
}

/**
 * Cognito placeholder — implement when AWS Cognito is wired.
 * @integration-point AUTH_COGNITO
 */
export const cognitoAuthProvider: AuthProvider = {
  async login() {
    throw new Error('Cognito authentication is not configured. Enable VITE_DEV_AUTH_ENABLED for local development.');
  },
  async logout() {
    return;
  },
  getSession() {
    return null;
  },
  async refreshSession() {
    return null;
  },
};
