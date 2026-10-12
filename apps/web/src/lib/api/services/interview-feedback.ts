import { get, post, put, type RequestOptions } from "../client";
import type {
  ApplicationSubmittedInterviewFeedbackList,
  InterviewFeedback,
  InterviewFeedbackDraftRequest,
  InterviewFeedbackSubmitRequest,
  InterviewFeedbackUpdateRequest,
  MyInterviewFeedbackResponse,
} from "@/types/api";

export async function getMyInterviewFeedback(
  interviewSessionId: string,
  options?: RequestOptions,
): Promise<MyInterviewFeedbackResponse> {
  return get<MyInterviewFeedbackResponse>(
    `/interview-sessions/${interviewSessionId}/my-feedback`,
    options,
  );
}

export async function listApplicationSubmittedInterviewFeedback(
  applicationId: string,
  options?: RequestOptions,
): Promise<ApplicationSubmittedInterviewFeedbackList> {
  return get<ApplicationSubmittedInterviewFeedbackList>(
    `/applications/${applicationId}/interview-feedback`,
    options,
  );
}

export async function createInterviewFeedbackDraft(
  interviewSessionId: string,
  body: InterviewFeedbackDraftRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewFeedback> {
  return post<InterviewFeedback>(
    `/interview-sessions/${interviewSessionId}/feedback`,
    body,
    { ...options, idempotencyKey },
  );
}

export async function updateInterviewFeedbackDraft(
  feedbackId: string,
  body: InterviewFeedbackUpdateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewFeedback> {
  return put<InterviewFeedback>(`/interview-feedback/${feedbackId}`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function submitInterviewFeedback(
  feedbackId: string,
  body: InterviewFeedbackSubmitRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<InterviewFeedback> {
  return post<InterviewFeedback>(
    `/interview-feedback/${feedbackId}/submit`,
    body,
    { ...options, idempotencyKey },
  );
}
