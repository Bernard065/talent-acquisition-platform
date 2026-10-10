import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  ApplicationResponse,
  ApplicationListResponse,
  ApplicationCreateRequest,
  ApplicationStatus,
  ApplicationRejectionReason,
  ApplicationPipelineListResponse,
} from "@/types/api";

export interface ApplicationSearchParams extends PaginationParams {
  query?: string;
  requisition_id?: string;
  candidate_id?: string;
  status?: ApplicationStatus;
  applied_after?: string;
  applied_before?: string;
}

export async function listApplications(
  params?: ApplicationSearchParams,
  options?: RequestOptions,
): Promise<ApplicationListResponse> {
  return get<ApplicationListResponse>("/applications", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function listApplicationPipeline(
  params?: ApplicationSearchParams,
  options?: RequestOptions,
): Promise<ApplicationPipelineListResponse> {
  return get<ApplicationPipelineListResponse>("/applications/pipeline", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getApplication(
  id: string,
  options?: RequestOptions,
): Promise<ApplicationResponse> {
  return get<ApplicationResponse>(`/applications/${id}`, options);
}

export async function createApplication(
  body: ApplicationCreateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationResponse> {
  return post<ApplicationResponse>("/applications", body, {
    ...options,
    idempotencyKey,
  });
}

export async function transitionApplicationStage(
  id: string,
  body: {
    target_status: ApplicationStatus;
    expected_version: number;
    rejection_reason?: ApplicationRejectionReason | null;
  },
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationResponse> {
  return post<ApplicationResponse>(`/applications/${id}/stage-transitions`, body, {
    ...options,
    idempotencyKey,
  });
}
