import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  JobPostingResponse,
  JobPostingListResponse,
  CreateJobPostingRequest,
  ExpectedJobPostingVersionRequest,
  PublicJobDetailResponse,
  PublicJobListResponse,
} from "@/types/api";

export async function listJobPostings(
  params?: PaginationParams,
  options?: RequestOptions,
): Promise<JobPostingListResponse> {
  return get<JobPostingListResponse>("/job-postings", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getJobPosting(
  id: string,
  options?: RequestOptions,
): Promise<JobPostingResponse> {
  return get<JobPostingResponse>(`/job-postings/${id}`, options);
}

export async function createJobPostingFromRequisition(
  requisitionId: string,
  body: CreateJobPostingRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<JobPostingResponse> {
  return post<JobPostingResponse>(`/requisitions/${requisitionId}/job-postings`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function publishJobPosting(
  id: string,
  body: ExpectedJobPostingVersionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<JobPostingResponse> {
  return post<JobPostingResponse>(`/job-postings/${id}/publish`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function unpublishJobPosting(
  id: string,
  body: ExpectedJobPostingVersionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<JobPostingResponse> {
  return post<JobPostingResponse>(`/job-postings/${id}/unpublish`, body, {
    ...options,
    idempotencyKey,
  });
}

// ---------------------------------------------------------------------------
// Public Jobs
// ---------------------------------------------------------------------------

export async function listPublicJobs(
  params?: PaginationParams,
  options?: RequestOptions,
): Promise<PublicJobListResponse> {
  return get<PublicJobListResponse>("/public/jobs", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getPublicJob(
  publicId: string,
  slug: string,
  options?: RequestOptions,
): Promise<PublicJobDetailResponse> {
  // Public jobs use a specific route matching the SEO canonical URL structure
  return get<PublicJobDetailResponse>(`/jobs/${publicId}/${slug}`, options);
}
