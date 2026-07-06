import { env } from '../config/env';

export type RequestOptions = RequestInit & {
  /** Skip JSON content-type header for multipart uploads. */
  rawBody?: boolean;
};

/**
 * Base HTTP client for backend API calls.
 * @integration-point API_CLIENT
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { rawBody, headers, ...init } = options;

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: rawBody
      ? headers
      : {
          'Content-Type': 'application/json',
          ...headers,
        },
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
