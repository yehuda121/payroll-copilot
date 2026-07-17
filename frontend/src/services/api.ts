import { env } from '../config/env';
import { getPortalAuthHeaders } from '../lib/auth/access-token';
import { getAuthHeaders } from '../lib/guest/guest-session';
import { readStoredLocale } from '../i18n';

export type RequestOptions = RequestInit & {
  rawBody?: boolean;
  /** Attach guest Bearer token when true. */
  auth?: boolean;
  /** Attach portal/employee JWT when true. */
  portalAuth?: boolean;
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

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { rawBody, auth = false, portalAuth = false, headers, ...init } = options;
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
    throw new ApiClientError(message, response.status, code, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
