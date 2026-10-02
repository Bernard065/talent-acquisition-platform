/**
 * Shared utility types for API communication.
 */

/** Shape of every error body returned by the backend. */
export interface ApiErrorBody {
  detail: string;
  request_id?: string;
}

/** Cursor-paginated list returned by backend list endpoints. */
export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

/** Common query parameters accepted by paginated list endpoints. */
export interface PaginationParams {
  cursor?: string;
  limit?: number;
}

/** HTTP methods used by the API client. */
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
