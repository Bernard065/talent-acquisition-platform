import { apiRequest, get, post, type RequestOptions } from "../client";
import type {
  CreateHrisConnectionRequest,
  HrisConnectionListResponse,
  HrisConnectionResponse,
  HrisHandoffOperationListResponse,
  HrisHandoffOperationResponse,
} from "@/types/api/hris";

export function listHrisConnections(options?: RequestOptions) {
  return get<HrisConnectionListResponse>("/hris-connections", options);
}

export function createHrisConnection(
  request: CreateHrisConnectionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<HrisConnectionResponse>("/hris-connections", request, {
    ...options,
    idempotencyKey,
  });
}

export function disableHrisConnection(
  id: string,
  expectedVersion: number,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<HrisConnectionResponse>(
    `/hris-connections/${id}/disable`,
    { expected_version: expectedVersion },
    { ...options, idempotencyKey },
  );
}

export function deleteHrisConnection(
  id: string,
  expectedVersion: number,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return apiRequest<{ id: string; status: string }>(
    "DELETE",
    `/hris-connections/${id}`,
    { expected_version: expectedVersion },
    { ...options, idempotencyKey },
  );
}

export function listHrisHandoffs(
  params: { limit?: number; cursor?: string; status?: string } = {},
  options?: RequestOptions,
) {
  return get<HrisHandoffOperationListResponse>("/hris/handoffs", {
    ...options,
    params,
  });
}

export function retryHrisHandoff(
  id: string,
  expectedVersion: number,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<HrisHandoffOperationResponse>(
    `/hris/handoffs/${id}/retry`,
    { expected_version: expectedVersion },
    { ...options, idempotencyKey },
  );
}
