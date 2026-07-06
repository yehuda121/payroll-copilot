/**
 * Frontend environment configuration.
 * Vite exposes only variables prefixed with VITE_.
 */

export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  devAuthEnabled: import.meta.env.VITE_DEV_AUTH_ENABLED === 'true',
} as const;
