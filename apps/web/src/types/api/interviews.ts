export type InterviewSessionStatus = "scheduled" | "completed" | "cancelled";
export type InterviewParticipantRole = "interviewer" | "coordinator";

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
  participants: InterviewParticipantRequest[];
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
  status: InterviewSessionStatus;
  completed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: InterviewCancellationReason | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface InterviewSearchResultResponse extends InterviewSessionResponse {
  participants: InterviewParticipantSummaryResponse[];
}

export interface InterviewSearchListResponse {
  items: InterviewSearchResultResponse[];
  next_cursor?: string | null;
}
