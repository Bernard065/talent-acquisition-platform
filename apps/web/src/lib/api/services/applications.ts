import { get, post, put, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  ApplicationResponse,
  ApplicationAssignmentRequest,
  ApplicationFollowUp,
  ApplicationFollowUpCompleteRequest,
  ApplicationFollowUpListResponse,
  ApplicationFollowUpRequest,
  ApplicationFollowUpUpdateRequest,
  ApplicationActivityResponse,
  ApplicationListResponse,
  ApplicationCreateRequest,
  ApplicationStatus,
  ApplicationRejectionReason,
  ApplicationPipelineListResponse,
  ApplicationPipelineSummaryResponse,
} from "@/types/api";

export interface ApplicationSearchParams extends PaginationParams {
  query?: string;
  requisition_id?: string;
  candidate_id?: string;
  status?: ApplicationStatus;
  applied_after?: string;
  applied_before?: string;
  mine?: boolean;
  follow_up?: "due";
}

export type ApplicationFilterParams = Omit<ApplicationSearchParams, "cursor" | "limit">;

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

export async function getApplicationPipelineSummary(
  params?: ApplicationFilterParams,
  options?: RequestOptions,
): Promise<ApplicationPipelineSummaryResponse> {
  return get<ApplicationPipelineSummaryResponse>("/applications/pipeline/summary", {
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

export async function getApplicationActivity(
  id: string,
  options?: RequestOptions,
): Promise<ApplicationActivityResponse> {
  return get<ApplicationActivityResponse>(`/applications/${id}/activity`, options);
}

export async function assignApplication(
  id: string,
  body: ApplicationAssignmentRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationResponse> {
  return post<ApplicationResponse>(`/applications/${id}/assignment`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function listApplicationFollowUps(
  id: string,
  options?: RequestOptions,
): Promise<ApplicationFollowUpListResponse> {
  return get<ApplicationFollowUpListResponse>(`/applications/${id}/follow-ups`, options);
}

export async function createApplicationFollowUp(
  id: string,
  body: ApplicationFollowUpRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationFollowUp> {
  return post<ApplicationFollowUp>(`/applications/${id}/follow-ups`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function updateApplicationFollowUp(
  applicationId: string,
  followUpId: string,
  body: ApplicationFollowUpUpdateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationFollowUp> {
  return put<ApplicationFollowUp>(
    `/applications/${applicationId}/follow-ups/${followUpId}`,
    body,
    { ...options, idempotencyKey },
  );
}

export async function completeApplicationFollowUp(
  applicationId: string,
  followUpId: string,
  body: ApplicationFollowUpCompleteRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationFollowUp> {
  return post<ApplicationFollowUp>(
    `/applications/${applicationId}/follow-ups/${followUpId}/complete`,
    body,
    { ...options, idempotencyKey },
  );
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
