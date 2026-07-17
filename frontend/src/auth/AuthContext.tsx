import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { env } from '../config/env';
import { clearAccessToken, saveAccessToken } from '../lib/auth/access-token';
import { apiRequest } from '../services/api';
import { employeePortalService } from '../services/employeePortal';
import type { AuthSession, LoginCredentials, UserRole } from '../types/auth';
import {
  clearCognitoSession,
  cognitoAuthProvider,
  loadCognitoSession,
} from './authProvider';
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

function initialSession(): AuthSession | null {
  if (env.devAuthEnabled) {
    return loadDevSession();
  }
  return loadCognitoSession();
}

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
  const [session, setSession] = useState<AuthSession | null>(() => initialSession());

  const loginWithDevRole = useCallback(async (role: UserRole) => {
    if (!env.devAuthEnabled) {
      throw new Error('Dev role login is disabled. Sign in with Cognito credentials.');
    }
    clearCognitoSession();
    const next = devLoginAsRole(role);
    if (role === 'employee') {
      const token = await fetchDevEmployeeAccessToken();
      if (!token) {
        clearAccessToken();
        throw new Error(
          'Employee portal token could not be issued. Cognito may be enabled, or seed data is missing.',
        );
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
        // Keep seeded display name if /me is temporarily unavailable.
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
    clearDevSession();
    const next = await cognitoAuthProvider.login(credentials);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    clearDevSession();
    clearCognitoSession();
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
