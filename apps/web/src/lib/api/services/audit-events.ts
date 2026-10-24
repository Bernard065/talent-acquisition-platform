import { get, type RequestOptions } from "../client";
import type {
  AuditEventListResponse,
  AuditEventSearchParams,
} from "@/types/api/audit-events";

export function listAuditEvents(
  params: AuditEventSearchParams,
  options?: RequestOptions,
): Promise<AuditEventListResponse> {
  return get<AuditEventListResponse>("/audit-events", {
    ...options,
    params: { ...options?.params, ...params },
  });
}
