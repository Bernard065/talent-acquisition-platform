import { get, post, type RequestOptions } from "../client";
import type {
  CalendarSyncOperationsListResponse,
  InterviewCalendarSyncStatus,
  InterviewCalendarSyncRetryResponse,
} from "@/types/api";

export interface CalendarSyncOperationsParams {
  limit?: number;
  offset?: number;
  status?: InterviewCalendarSyncStatus;
}

export function listCalendarSyncOperations(
  params: CalendarSyncOperationsParams = {},
  options?: RequestOptions,
): Promise<CalendarSyncOperationsListResponse> {
  return get<CalendarSyncOperationsListResponse>("/operations/calendar-syncs", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export function retryCalendarSyncOperation(
  interviewSessionId: string,
  options?: RequestOptions,
): Promise<InterviewCalendarSyncRetryResponse> {
  return post<InterviewCalendarSyncRetryResponse>(
    `/operations/calendar-syncs/${interviewSessionId}/retry`,
    {},
    options,
  );
}
