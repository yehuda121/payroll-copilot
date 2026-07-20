/**
 * Frontend environment configuration.
 * Vite exposes only variables prefixed with VITE_.
 */

const devAuthEnabled = import.meta.env.VITE_DEV_AUTH_ENABLED === 'true';

if (import.meta.env.PROD && devAuthEnabled) {
  throw new Error(
    'VITE_DEV_AUTH_ENABLED must be false in production builds. ' +
      'Refusing to start with development authentication enabled.',
  );
}

export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  /** True only in Vite development server builds — never in production bundles. */
  isDevRuntime: import.meta.env.DEV,
  devAuthEnabled,
} as const;
