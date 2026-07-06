/**
 * Development-only authentication.
 * Isolated from payroll business logic — swap out via authProvider.ts for production.
 */

import type { AuthSession, AuthUser, UserRole } from '../types/auth';

const STORAGE_KEY = 'payroll_copilot_dev_session';

/** Realistic dev identities for role-based UI testing. */
export const DEV_IDENTITIES: Record<UserRole, AuthUser> = {
  employee: {
    id: 'dev-emp-001',
    email: 'sarah.cohen@dev.payroll-copilot.local',
    fullName: 'Sarah Cohen',
    role: 'employee',
    organizationId: 'dev-org-001',
  },
  payroll_accountant: {
    id: 'dev-acc-001',
    email: 'david.levy@dev.payroll-copilot.local',
    fullName: 'David Levy',
    role: 'payroll_accountant',
    organizationId: 'dev-org-001',
  },
  developer_admin: {
    id: 'dev-admin-001',
    email: 'yael.admin@dev.payroll-copilot.local',
    fullName: 'Yael Administrator',
    role: 'developer_admin',
    organizationId: 'dev-org-001',
  },
};

export function createDevSession(role: UserRole): AuthSession {
  return {
    user: DEV_IDENTITIES[role],
    provider: 'dev',
    issuedAt: new Date().toISOString(),
  };
}

export function loadDevSession(): AuthSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveDevSession(session: AuthSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearDevSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function devLoginAsRole(role: UserRole): AuthSession {
  const session = createDevSession(role);
  saveDevSession(session);
  return session;
}

export function devLogout(): void {
  clearDevSession();
}
