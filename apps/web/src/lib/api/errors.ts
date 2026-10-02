/**
 * Typed error class for API responses.
 *
 * The backend returns RFC-7807-style error bodies with a consistent shape:
 * `{ detail: string; request_id: string }`.
 */
export class ApiError extends Error {
  /** HTTP status code. */
  readonly status: number;

  /** Human-readable error detail from the backend. */
  readonly detail: string;

  /** Backend-assigned request identifier for traceability. */
  readonly requestId: string | undefined;

  constructor(status: number, detail: string, requestId?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }

  /** True when the error indicates an authentication failure. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True when the error indicates insufficient permissions. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** True when the requested resource was not found. */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** True when the error is a state or version conflict. */
  get isConflict(): boolean {
    return this.status === 409;
  }

  /** True when the error is a validation failure. */
  get isValidationError(): boolean {
    return this.status === 422;
  }

  /** True when the backend asks the client to retry after some delay. */
  get isRetryable(): boolean {
    return this.status === 503;
  }
}
