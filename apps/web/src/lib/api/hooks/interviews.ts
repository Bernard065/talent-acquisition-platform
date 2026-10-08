"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  cancelInterview,
  getInterview,
  listInterviews,
  scheduleInterview,
  type InterviewSearchParams,
} from "../services/interviews";
import type {
  InterviewCancellationReason,
  InterviewSessionResponse,
  ScheduleInterviewRequest,
} from "@/types/api";

export const interviewQueryKeys = {
  all: ["interviews"] as const,
  lists: () => [...interviewQueryKeys.all, "list"] as const,
  list: (params: InterviewSearchParams = {}) =>
    [...interviewQueryKeys.lists(), params] as const,
  detail: (id: string) => [...interviewQueryKeys.all, "detail", id] as const,
};

export function useInterviews(params: InterviewSearchParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: interviewQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listInterviews({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useInterview(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: interviewQueryKeys.detail(id),
    queryFn: ({ signal }) => getInterview(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useScheduleInterview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ applicationId, interview, idempotencyKey }: {
      applicationId: string;
      interview: ScheduleInterviewRequest;
      idempotencyKey: string;
    }) => scheduleInterview(applicationId, interview, idempotencyKey),
    onSuccess: async (interview) => {
      queryClient.setQueryData(interviewQueryKeys.detail(interview.id), interview);
      await queryClient.invalidateQueries({ queryKey: interviewQueryKeys.lists() });
    },
  });
}

export function useCancelInterview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ interview, cancellationReason, idempotencyKey }: {
      interview: Pick<InterviewSessionResponse, "id" | "version">;
      cancellationReason: InterviewCancellationReason;
      idempotencyKey: string;
    }) => cancelInterview(
      interview.id,
      {
        expected_version: interview.version,
        cancellation_reason: cancellationReason,
      },
      idempotencyKey,
    ),
    onSuccess: async (interview) => {
      queryClient.setQueryData(interviewQueryKeys.detail(interview.id), interview);
      await queryClient.invalidateQueries({ queryKey: interviewQueryKeys.lists() });
    },
  });
}
