import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  CandidateResponse,
  CandidateListResponse,
  CandidateCreateRequest,
  CandidatePrivacyOperationResponse,
} from "@/types/api";

export async function listCandidates(
  params?: PaginationParams,
  options?: RequestOptions,
): Promise<CandidateListResponse> {
  return get<CandidateListResponse>("/candidates", {
    ...options,
    params: { ...options?.params, ...params } as Record<string, string>,
  });
}

export async function getCandidate(
  id: string,
  options?: RequestOptions,
): Promise<CandidateResponse> {
  return get<CandidateResponse>(`/candidates/${id}`, options);
}

export async function createCandidate(
  body: CandidateCreateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<CandidateResponse> {
  return post<CandidateResponse>("/candidates", body, {
    ...options,
    idempotencyKey,
  });
}

export async function requestCandidateErasure(
  id: string,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<CandidatePrivacyOperationResponse> {
  return post<CandidatePrivacyOperationResponse>(
    `/candidates/${id}/erasure-requests`,
    undefined,
    {
      ...options,
      idempotencyKey,
    },
  );
}
