import { get, post, patch, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  RequisitionResponse,
  RequisitionListResponse,
  RequisitionCreateRequest,
  RequisitionUpdateRequest,
  RequisitionTransitionRequest,
} from "@/types/api";

export async function listRequisitions(
  params?: PaginationParams,
  options?: RequestOptions,
): Promise<RequisitionListResponse> {
  return get<RequisitionListResponse>("/requisitions", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getRequisition(
  id: string,
  options?: RequestOptions,
): Promise<RequisitionResponse> {
  return get<RequisitionResponse>(`/requisitions/${id}`, options);
}

export async function createRequisition(
  body: RequisitionCreateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionResponse> {
  return post<RequisitionResponse>("/requisitions", body, {
    ...options,
    idempotencyKey,
  });
}

export async function updateRequisition(
  id: string,
  body: RequisitionUpdateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionResponse> {
  return patch<RequisitionResponse>(`/requisitions/${id}`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function transitionRequisition(
  id: string,
  body: RequisitionTransitionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionResponse> {
  return post<RequisitionResponse>(`/requisitions/${id}/transitions`, body, {
    ...options,
    idempotencyKey,
  });
}
