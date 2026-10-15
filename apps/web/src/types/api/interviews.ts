import type {
  CalendarConnectionStatus,
  CalendarProvider,
} from "./calendar-connections";

export type InterviewSessionStatus = "scheduled" | "completed" | "cancelled";
export type InterviewParticipantRole = "interviewer" | "coordinator";
export type InterviewFormat = "online" | "in_person";

export const INTERVIEW_CANCELLATION_REASONS = [
  "candidate_withdrew",
  "candidate_unavailable",
  "interviewer_unavailable",
  "requisition_closed",
  "scheduling_conflict",
  "other",
] as const;

export type InterviewCancellationReason =
  (typeof INTERVIEW_CANCELLATION_REASONS)[number];

export interface InterviewParticipantRequest {
  user_id: string;
  role: InterviewParticipantRole;
}

export interface ScheduleInterviewRequest {
  scheduled_start_at: string;
  scheduled_end_at: string;
  format?: InterviewFormat | null;
  meeting_url?: string | null;
  location?: string | null;
  participants: InterviewParticipantRequest[];
}

export interface CompleteInterviewSessionRequest {
  expected_version: number;
}

export interface InterviewParticipantSummaryResponse {
  user_id: string;
  role: InterviewParticipantRole;
}

export interface InterviewSessionResponse {
  id: string;
  application_id: string;
  scheduled_start_at: string;
  scheduled_end_at: string;
  format: InterviewFormat | null;
  meeting_url: string | null;
  location: string | null;
  status: InterviewSessionStatus;
  completed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: InterviewCancellationReason | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export type InterviewCalendarSyncStatus = "pending" | "synced" | "failed" | "disabled";

export interface InterviewCalendarSync {
  calendar_owner_display_name: string;
  provider: CalendarProvider;
  connection_status: CalendarConnectionStatus;
  status: InterviewCalendarSyncStatus;
  delivery_state:
    | "queued"
    | "syncing"
    | "synced"
    | "failed"
    | "disabled"
    | "worker_unavailable"
    | "not_queued";
  last_error_code: string | null;
  last_attempt_at: string | null;
  synced_at: string | null;
}

export interface InterviewCalendarSyncListResponse {
  items: InterviewCalendarSync[];
  can_retry: boolean;
  worker_available: boolean;
  worker_last_seen_at: string | null;
  queue_status: "pending" | "processing" | "processed" | "dead_lettered" | null;
  queued_at: string | null;
}

export interface InterviewCalendarSyncRetryResponse {
  status: "queued";
}

export interface CalendarSyncOperationItem {
  id: string;
  interview_session_id: string;
  interview_title: string;
  scheduled_start_at: string;
  calendar_owner_display_name: string;
  provider: CalendarProvider;
  connection_status: CalendarConnectionStatus;
  sync_status: InterviewCalendarSyncStatus;
  outbox_status: "pending" | "processing" | "processed" | "dead_lettered" | null;
  attempts: number;
  last_error_code: string | null;
  last_attempt_at: string | null;
  synced_at: string | null;
  can_retry: boolean;
}

export interface CalendarSyncOperationsListResponse {
  items: CalendarSyncOperationItem[];
  total: number;
  limit: number;
  offset: number;
  worker_available: boolean;
  worker_last_seen_at: string | null;
}

export type InterviewFeedbackStatus = "draft" | "submitted";
export type InterviewRecommendation = "strong_no" | "no" | "yes" | "strong_yes";

export interface InterviewFeedback {
  id: string;
  interview_session_id: string;
  status: InterviewFeedbackStatus;
  overall_rating: number | null;
  recommendation: InterviewRecommendation | null;
  strengths: string | null;
  concerns: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface MyInterviewFeedbackResponse {
  feedback: InterviewFeedback | null;
}

export interface InterviewFeedbackDraftRequest {
  overall_rating?: number | null;
  recommendation?: InterviewRecommendation | null;
  strengths?: string | null;
  concerns?: string | null;
}

export interface InterviewFeedbackUpdateRequest extends InterviewFeedbackDraftRequest {
  expected_version: number;
}

export interface InterviewFeedbackSubmitRequest extends InterviewFeedbackUpdateRequest {
  overall_rating: number;
  recommendation: InterviewRecommendation;
}

export interface ApplicationSubmittedInterviewFeedback {
  id: string;
  interview_session_id: string;
  scheduled_start_at: string;
  interviewer_display_name: string;
  status: "submitted";
  overall_rating: number;
  recommendation: InterviewRecommendation;
  strengths: string | null;
  concerns: string | null;
  submitted_at: string;
}

export interface ApplicationSubmittedInterviewFeedbackList {
  items: ApplicationSubmittedInterviewFeedback[];
}

export interface InterviewSearchResultResponse extends InterviewSessionResponse {
  participants: InterviewParticipantSummaryResponse[];
}

export interface InterviewSearchListResponse {
  items: InterviewSearchResultResponse[];
  next_cursor?: string | null;
}
