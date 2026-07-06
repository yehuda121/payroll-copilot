import type { GuestSessionResponse, LoginCredentials } from '../types';
import { apiRequest } from './api';

/**
 * Authentication service.
 * Production: replace dev flow with Cognito via authProvider.ts.
 * @integration-point AUTH_SERVICE
 */
export const authService = {
  async createGuestSession(): Promise<GuestSessionResponse> {
    return apiRequest<GuestSessionResponse>('/auth/guest/session', { method: 'POST' });
  },

  async login(_credentials: LoginCredentials): Promise<void> {
    // @integration-point AUTH_LOGIN — POST /auth/login when Cognito/JWT is wired
    throw new Error('Production login is not connected. Enable VITE_DEV_AUTH_ENABLED for development.');
  },

  async logout(): Promise<void> {
    // @integration-point AUTH_LOGOUT
    return;
  },
};
