import type { GuestSessionResponse } from '../types';
import { apiRequest } from './api';
import { setGuestSession } from '../lib/guest/guest-session';

export const authService = {
  async createGuestSession(): Promise<GuestSessionResponse> {
    const response = await apiRequest<GuestSessionResponse>('/auth/guest/session', {
      method: 'POST',
    });
    setGuestSession(response.guest_token, response.expires_at);
    return response;
  },
};
