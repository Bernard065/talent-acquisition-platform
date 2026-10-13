"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { notificationQueryKeys } from "./notifications";
import {
  createInterviewFeedbackDraft,
  getMyInterviewFeedback,
  listApplicationSubmittedInterviewFeedback,
  submitInterviewFeedback,
  updateInterviewFeedbackDraft,
} from "../services/interview-feedback";
import type {
  InterviewFeedbackDraftRequest,
  InterviewFeedbackSubmitRequest,
  InterviewFeedbackUpdateRequest,
} from "@/types/api";

export const interviewFeedbackQueryKeys = {
  all: ["interview-feedback"] as const,
  mine: (sessionId: string) => [...interviewFeedbackQueryKeys.all, "mine", sessionId] as const,
  applications: () => [...interviewFeedbackQueryKeys.all, "application"] as const,
  application: (applicationId: string) =>
    [...interviewFeedbackQueryKeys.applications(), applicationId] as const,
};

export function useMyInterviewFeedback(sessionId: string, enabled = true) {
  const { status } = useSession();

  return useQuery({
    queryKey: interviewFeedbackQueryKeys.mine(sessionId),
    queryFn: ({ signal }) => getMyInterviewFeedback(sessionId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(sessionId),
  });
}

export function useApplicationSubmittedInterviewFeedback(
  applicationId: string,
  enabled = true,
) {
  const { status } = useSession();

  return useQuery({
    queryKey: interviewFeedbackQueryKeys.application(applicationId),
    queryFn: ({ signal }) => listApplicationSubmittedInterviewFeedback(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
  });
}

function useInvalidateInterviewFeedback() {
  const queryClient = useQueryClient();
  return async (sessionId: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: interviewFeedbackQueryKeys.mine(sessionId) }),
      queryClient.invalidateQueries({ queryKey: interviewFeedbackQueryKeys.applications() }),
      queryClient.invalidateQueries({ queryKey: notificationQueryKeys.actionItems }),
    ]);
  };
}

export function useCreateInterviewFeedbackDraft() {
  const invalidate = useInvalidateInterviewFeedback();
  return useMutation({
    mutationFn: ({ sessionId, feedback, idempotencyKey }: {
      sessionId: string;
      feedback: InterviewFeedbackDraftRequest;
      idempotencyKey: string;
    }) => createInterviewFeedbackDraft(sessionId, feedback, idempotencyKey),
    onSuccess: async (_feedback, { sessionId }) => invalidate(sessionId),
  });
}

export function useUpdateInterviewFeedbackDraft() {
  const invalidate = useInvalidateInterviewFeedback();
  return useMutation({
    mutationFn: ({ feedbackId, feedback, idempotencyKey }: {
      sessionId: string;
      feedbackId: string;
      feedback: InterviewFeedbackUpdateRequest;
      idempotencyKey: string;
    }) => updateInterviewFeedbackDraft(feedbackId, feedback, idempotencyKey),
    onSuccess: async (_feedback, { sessionId }) => invalidate(sessionId),
  });
}

export function useSubmitInterviewFeedback() {
  const invalidate = useInvalidateInterviewFeedback();
  return useMutation({
    mutationFn: ({ feedbackId, feedback, idempotencyKey }: {
      sessionId: string;
      feedbackId: string;
      feedback: InterviewFeedbackSubmitRequest;
      idempotencyKey: string;
    }) => submitInterviewFeedback(feedbackId, feedback, idempotencyKey),
    onSuccess: async (_feedback, { sessionId }) => invalidate(sessionId),
  });
}
