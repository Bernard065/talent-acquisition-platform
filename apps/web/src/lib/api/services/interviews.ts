import { get, post, type RequestOptions } from "../client";
import type { PaginationParams } from "../types";
import type {
  InterviewSessionResponse,
  InterviewSearchListResponse,
  ScheduleInterviewRequest,
  InterviewCancellationReason,
  InterviewSessionStatus,
} from "@/types/api";

export interface InterviewSearchParams extends PaginationParams {
  application_id?: string;
  participant_user_id?: string;
  status?: InterviewSessionStatus;
  scheduled_after?: string;
  scheduled_before?: string;
}

export async function listInterviews(
  params?: InterviewSearchParams,
  options?: RequestOptions,
): Promise<InterviewSearchListResponse> {
  return get<InterviewSearchListResponse>("/interviews", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export async function getInterview(
  id: string,
  options?: RequestOptions,
): Promise<InterviewSessionResponse> {
  return get<InterviewSessionResponse>(`/interviews/${id}`, options);
}

export async function scheduleInterview(
  applicationId: string,
  body: ScheduleInterviewRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewSessionResponse> {
  return post<InterviewSessionResponse>(`/applications/${applicationId}/interviews`, body, {
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
  return post<InterviewSessionResponse>(`/interview-sessions/${id}/cancel`, body, {
    ...options,
    idempotencyKey,
  });
}
