import { env } from '../config/env';
import { getAuthHeaders } from '../lib/guest/guest-session';
import { readStoredLocale } from '../i18n';

export type RequestOptions = RequestInit & {
  rawBody?: boolean;
  auth?: boolean;
};

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { rawBody, auth = false, headers, ...init } = options;
  const locale = readStoredLocale();

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: rawBody
      ? {
          'Accept-Language': locale,
          ...(auth ? getAuthHeaders() : {}),
          ...headers,
        }
      : {
          'Content-Type': 'application/json',
          'Accept-Language': locale,
          ...(auth ? getAuthHeaders() : {}),
          ...headers,
        },
  });

  if (!response.ok) {
    let message = `API request failed: ${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep default message when response is not JSON.
    }
    throw new ApiClientError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
