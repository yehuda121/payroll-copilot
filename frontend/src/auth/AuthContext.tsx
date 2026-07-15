import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { env } from '../config/env';
import { clearAccessToken, saveAccessToken } from '../lib/auth/access-token';
import { apiRequest } from '../services/api';
import { employeePortalService } from '../services/employeePortal';
import type { AuthSession, LoginCredentials, UserRole } from '../types/auth';
import { cognitoAuthProvider } from './authProvider';
import { clearDevSession, devLoginAsRole, loadDevSession, saveDevSession } from './devAuth';

type AuthContextValue = {
  session: AuthSession | null;
  isAuthenticated: boolean;
  devAuthEnabled: boolean;
  loginWithCredentials: (credentials: LoginCredentials) => Promise<void>;
  loginWithDevRole: (role: UserRole) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchDevEmployeeAccessToken(): Promise<string | null> {
  try {
    const result = await apiRequest<{ access_token: string }>('/auth/dev/employee-session', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    return result.access_token;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(() =>
    env.devAuthEnabled ? loadDevSession() : null,
  );

  const loginWithDevRole = useCallback(async (role: UserRole) => {
    const next = devLoginAsRole(role);
    if (role === 'employee') {
      const token = await fetchDevEmployeeAccessToken();
      if (!token) {
        clearAccessToken();
        throw new Error('Employee portal token could not be issued. Is the API running with seed data?');
      }
      saveAccessToken(token);
      next.accessToken = token;
      try {
        const me = await employeePortalService.me();
        next.user = {
          ...next.user,
          id: me.employee_id,
          fullName: me.full_name,
          localizedFullName: me.full_name_localized || me.full_name,
          organizationId: me.organization_id,
        };
      } catch {
        // Keep seeded Yehuda display name if /me is temporarily unavailable.
      }
      saveDevSession(next);
    } else {
      clearAccessToken();
      saveDevSession(next);
    }
    setSession(next);
  }, []);

  const loginWithCredentials = useCallback(async (credentials: LoginCredentials) => {
    if (env.devAuthEnabled) {
      throw new Error('Use dev role login when VITE_DEV_AUTH_ENABLED is true.');
    }
    const next = await cognitoAuthProvider.login(credentials);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    clearDevSession();
    clearAccessToken();
    setSession(null);
    void cognitoAuthProvider.logout();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: session !== null,
      devAuthEnabled: env.devAuthEnabled,
      loginWithCredentials,
      loginWithDevRole,
      logout,
    }),
    [session, loginWithCredentials, loginWithDevRole, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
