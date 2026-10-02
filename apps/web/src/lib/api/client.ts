/**
 * Core API client for communicating with the FastAPI backend.
 *
 * Uses native `fetch` (extended by Next.js with caching and revalidation).
 * All mutating requests attach an `Idempotency-Key` header. Error responses
 * are parsed into {@link ApiError} instances.
 */

import { ApiError } from "./errors";
import type { ApiErrorBody, HttpMethod } from "./types";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const isServer = typeof window === "undefined";
const API_BASE_URL = isServer
  ? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
  : ""; // Browser requests go to Next.js proxy to attach httpOnly cookies
const API_PREFIX = "/api/v1";

// ---------------------------------------------------------------------------
// Token accessor — set by the auth provider at runtime
// ---------------------------------------------------------------------------

type TokenAccessor = () => string | null;

let _getToken: TokenAccessor = () => null;

/**
 * Register a function that returns the current bearer token.
 * Called once by the auth provider during initialization.
 */
export function setTokenAccessor(accessor: TokenAccessor): void {
  _getToken = accessor;
}

// ---------------------------------------------------------------------------
// Request helpers
// ---------------------------------------------------------------------------

/** Methods that carry a request body and require an idempotency key. */
const MUTATING_METHODS = new Set<HttpMethod>(["POST", "PUT", "PATCH", "DELETE"]);

function buildUrl(path: string, params?: Record<string, string>): string {
  const url = new URL(`${API_PREFIX}${path}`, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  return url.toString();
}

function buildHeaders(
  method: HttpMethod,
  idempotencyKey?: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (isServer) {
    // In Server Components, pull the token directly from cookies
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { cookies } = require("next/headers");
      const cookieStore = cookies();
      const token = cookieStore.get("auth_token")?.value;
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
    } catch {
      // Ignore errors if used outside of Next.js server context
    }
  } else {
    // In the browser, the middleware will inject the token into the proxied request.
    // We can also allow the token accessor as a fallback if set manually.
    const token = _getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  if (MUTATING_METHODS.has(method) && idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }

  return headers;
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  try {
    const body: ApiErrorBody = await response.json();
    return new ApiError(response.status, body.detail, body.request_id);
  } catch {
    return new ApiError(
      response.status,
      response.statusText || "An unexpected error occurred.",
    );
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface RequestOptions {
  /** Query parameters appended to the URL. */
  params?: Record<string, string>;

  /** Idempotency key for mutating requests. */
  idempotencyKey?: string;

  /** Next.js fetch options (caching, revalidation, tags). */
  next?: NextFetchRequestConfig;

  /** AbortSignal for request cancellation. */
  signal?: AbortSignal;
}

/**
 * Make a typed request to the backend API.
 *
 * @param method   HTTP method.
 * @param path     Path relative to `/api/v1` (e.g. `/requisitions`).
 * @param body     Optional JSON body for mutating requests.
 * @param options  Additional request options.
 * @returns        Parsed JSON response of type `T`.
 * @throws {ApiError} When the backend returns a non-2xx response.
 */
export async function apiRequest<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = buildUrl(path, options.params);
  const headers = buildHeaders(method, options.idempotencyKey);

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: options.signal,
    next: options.next,
  });

  if (!response.ok) {
    throw await parseErrorBody(response);
  }

  // 204 No Content — return undefined as T.
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Convenience wrappers
// ---------------------------------------------------------------------------

/** GET request — read a resource or list. */
export function get<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("GET", path, undefined, options);
}

/** POST request — create a resource. */
export function post<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return apiRequest<T>("POST", path, body, options);
}

/** PUT request — replace a resource. */
export function put<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return apiRequest<T>("PUT", path, body, options);
}

/** PATCH request — partially update a resource. */
export function patch<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return apiRequest<T>("PATCH", path, body, options);
}

/** DELETE request — remove a resource. */
export function del<T = void>(
  path: string,
  options?: RequestOptions,
): Promise<T> {
  return apiRequest<T>("DELETE", path, undefined, options);
}
