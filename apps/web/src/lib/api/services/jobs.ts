import { get, post, put, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  JobPostingResponse,
  JobPostingListResponse,
  CreateJobPostingRequest,
  ExpectedJobPostingVersionRequest,
  PublicJobDetailResponse,
  PublicJobListResponse,
  JobApplicationQuestionsResponse,
  ReplaceJobApplicationQuestionsRequest,
} from "@/types/api";
import type {
  ReplaceScreeningRubricRequest,
  ScreeningRubricResponse,
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

export async function getJobApplicationQuestions(
  id: string,
  options?: RequestOptions,
): Promise<JobApplicationQuestionsResponse> {
  return get<JobApplicationQuestionsResponse>(
    `/job-postings/${id}/application-questions`,
    options,
  );
}

export async function replaceJobApplicationQuestions(
  id: string,
  body: ReplaceJobApplicationQuestionsRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<JobApplicationQuestionsResponse> {
  return put<JobApplicationQuestionsResponse>(
    `/job-postings/${id}/application-questions`,
    body,
    { ...options, idempotencyKey },
  );
}

export async function getJobScreeningRubric(
  id: string,
  options?: RequestOptions,
): Promise<ScreeningRubricResponse> {
  return get<ScreeningRubricResponse>(`/job-postings/${id}/screening-rubric`, options);
}

export async function replaceJobScreeningRubric(
  id: string,
  body: ReplaceScreeningRubricRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ScreeningRubricResponse> {
  return put<ScreeningRubricResponse>(
    `/job-postings/${id}/screening-rubric`,
    body,
    { ...options, idempotencyKey },
  );
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
  options?: RequestOptions,
): Promise<PublicJobDetailResponse> {
  return get<PublicJobDetailResponse>(`/public/jobs/${publicId}`, options);
}
