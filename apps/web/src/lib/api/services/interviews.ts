import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  InterviewSessionResponse,
  InterviewSearchListResponse,
  ScheduleInterviewRequest,
  InterviewCancellationReason,
} from "@/types/api";

export async function listInterviews(
  params?: PaginationParams,
  options?: RequestOptions,
): Promise<InterviewSearchListResponse> {
  return get<InterviewSearchListResponse>("/interviews/search", {
    ...options,
    params: { ...options?.params, ...params } as Record<string, string>,
  });
}

export async function getInterview(
  id: string,
  options?: RequestOptions,
): Promise<InterviewSessionResponse> {
  return get<InterviewSessionResponse>(`/interviews/${id}`, options);
}

export async function scheduleInterview(
  body: ScheduleInterviewRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewSessionResponse> {
  return post<InterviewSessionResponse>("/interviews", body, {
    ...options,
    idempotencyKey,
  });
}

export async function cancelInterview(
  id: string,
  body: {
    expected_version: number;
    cancellation_reason: InterviewCancellationReason;
  },
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewSessionResponse> {
  return post<InterviewSessionResponse>(`/interviews/${id}/cancel`, body, {
    ...options,
    idempotencyKey,
  });
}
