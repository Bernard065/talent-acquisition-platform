import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  CandidateResponse,
  CandidateConsentStatus,
  CandidateFilterOptionsResponse,
  CandidateListResponse,
  CandidateCreateRequest,
  CandidatePrivacyOperationResponse,
} from "@/types/api";

export interface CandidateSearchParams extends PaginationParams {
  query?: string;
  source?: string;
  location?: string;
  consent_status?: CandidateConsentStatus;
}

export async function listCandidates(
  params?: CandidateSearchParams,
  options?: RequestOptions,
): Promise<CandidateListResponse> {
  return get<CandidateListResponse>("/candidates", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getCandidateFilterOptions(
  options?: RequestOptions,
): Promise<CandidateFilterOptionsResponse> {
  return get<CandidateFilterOptionsResponse>("/candidates/filter-options", options);
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
    `/candidates/${id}/erasure`,
    undefined,
    {
      ...options,
      idempotencyKey,
    },
  );
}
