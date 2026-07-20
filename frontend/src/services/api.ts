import { env } from '../config/env';
import { clearAccessToken, getPortalAuthHeaders } from '../lib/auth/access-token';
import { getAuthHeaders } from '../lib/guest/guest-session';
import { readStoredLocale } from '../i18n';

export type RequestOptions = RequestInit & {
  rawBody?: boolean;
  /** Attach guest Bearer token when true. */
  auth?: boolean;
  /** Attach portal/employee JWT when true. */
  portalAuth?: boolean;
  /** Internal: skip automatic refresh-and-retry (prevents refresh loops). */
  skipPortalAuthRefresh?: boolean;
  /** Internal: set after one refresh retry to prevent loops. */
  _portalAuthRetried?: boolean;
  signal?: AbortSignal;
};

export class ApiClientError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let portalAuthRedirectInFlight = false;

function isAuthenticationFailure(status: number, message: string, code?: string): boolean {
  if (status === 401) return true;
  const normalizedCode = (code || '').toLowerCase();
  if (normalizedCode === 'invalid_token' || normalizedCode === 'unauthorized') return true;
  const normalized = message.toLowerCase();
  return (
    normalized.includes('invalid or expired access token') ||
    normalized.includes('invalid or expired cognito token') ||
    normalized.includes('invalid token') ||
    normalized.includes('token expired') ||
    normalized.includes('401 unauthorized') ||
    normalized === 'unauthorized'
  );
}

/** Reuse the same session clears as AuthContext.logout, then hard-navigate to Login. */
async function clearSessionAndRedirectToLogin(): Promise<void> {
  if (portalAuthRedirectInFlight) return;
  portalAuthRedirectInFlight = true;

  const [{ clearCognitoSession }, { clearDevSession }] = await Promise.all([
    import('../auth/authProvider'),
    import('../auth/devAuth'),
  ]);
  clearDevSession();
  clearCognitoSession();
  clearAccessToken();

  if (typeof window === 'undefined') return;
  const path = window.location.pathname;
  if (path === '/login' || path.startsWith('/login/')) return;
  window.location.replace('/login');
}

async function parseErrorResponse(response: Response): Promise<{
  message: string;
  code?: string;
  details?: unknown;
}> {
  let message = `API request failed: ${response.status} ${response.statusText}`;
  let code: string | undefined;
  let details: unknown;
  try {
    const body = (await response.json()) as {
      detail?: string | { code?: string; message?: string; [key: string]: unknown };
    };
    if (typeof body.detail === 'string') {
      message = body.detail;
    } else if (body.detail && typeof body.detail === 'object') {
      details = body.detail;
      code = body.detail.code;
      message = body.detail.message || message;
    }
  } catch {
    // Keep default message when response is not JSON.
  }
  return { message, code, details };
}

async function executePortalAuthRefresh(): Promise<boolean> {
  const { cognitoAuthProvider } = await import('../auth/authProvider');
  const refreshed = await cognitoAuthProvider.refreshSession();
  return refreshed !== null;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    rawBody,
    auth = false,
    portalAuth = false,
    skipPortalAuthRefresh = false,
    _portalAuthRetried = false,
    headers,
    ...init
  } = options;
  const locale = readStoredLocale();

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    signal: init.signal,
    headers: rawBody
      ? {
          'Accept-Language': locale,
          ...(auth ? getAuthHeaders() : {}),
          ...(portalAuth ? getPortalAuthHeaders() : {}),
          ...headers,
        }
      : {
          'Content-Type': 'application/json',
          'Accept-Language': locale,
          ...(auth ? getAuthHeaders() : {}),
          ...(portalAuth ? getPortalAuthHeaders() : {}),
          ...headers,
        },
  });

  if (!response.ok) {
    const { message, code, details } = await parseErrorResponse(response);

    if (
      portalAuth &&
      !skipPortalAuthRefresh &&
      !_portalAuthRetried &&
      isAuthenticationFailure(response.status, message, code)
    ) {
      const refreshed = await executePortalAuthRefresh();
      if (refreshed) {
        return apiRequest<T>(path, {
          ...options,
          _portalAuthRetried: true,
        });
      }
      await clearSessionAndRedirectToLogin();
      return new Promise<T>(() => undefined);
    }

    if (portalAuth && isAuthenticationFailure(response.status, message, code)) {
      await clearSessionAndRedirectToLogin();
      return new Promise<T>(() => undefined);
    }

    throw new ApiClientError(message, response.status, code, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
