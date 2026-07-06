import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { env } from '../config/env';
import type { AuthSession, LoginCredentials, UserRole } from '../types/auth';
import { cognitoAuthProvider } from './authProvider';
import { clearDevSession, devLoginAsRole, loadDevSession } from './devAuth';

type AuthContextValue = {
  session: AuthSession | null;
  isAuthenticated: boolean;
  devAuthEnabled: boolean;
  loginWithCredentials: (credentials: LoginCredentials) => Promise<void>;
  loginWithDevRole: (role: UserRole) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(() =>
    env.devAuthEnabled ? loadDevSession() : null,
  );

  const loginWithDevRole = useCallback((role: UserRole) => {
    const next = devLoginAsRole(role);
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
