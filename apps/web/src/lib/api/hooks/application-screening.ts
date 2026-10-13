"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { applicationQueryKeys } from "./applications";
import {
  getJobScreeningComparison,
  listApplicationScreeningAssessments,
  submitApplicationScreeningAssessment,
} from "../services/application-screening";
import type { ApplicationScreeningAssessmentRequest } from "@/types/api";

export const applicationScreeningQueryKeys = {
  all: ["application-screening-assessments"] as const,
  application: (applicationId: string) =>
    [...applicationScreeningQueryKeys.all, applicationId] as const,
  jobComparison: (jobPostingId: string) =>
    [...applicationScreeningQueryKeys.all, "job-comparison", jobPostingId] as const,
};

export function useJobScreeningComparison(jobPostingId: string) {
  const { status } = useSession();
  return useInfiniteQuery({
    queryKey: applicationScreeningQueryKeys.jobComparison(jobPostingId),
    queryFn: ({ pageParam, signal }) =>
      getJobScreeningComparison(
        jobPostingId,
        { limit: 50, cursor: pageParam },
        { signal },
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated" && Boolean(jobPostingId),
  });
}

export function useApplicationScreeningAssessments(applicationId: string) {
  const { status } = useSession();
  return useQuery({
    queryKey: applicationScreeningQueryKeys.application(applicationId),
    queryFn: ({ signal }) => listApplicationScreeningAssessments(applicationId, { signal }),
    enabled: status === "authenticated" && Boolean(applicationId),
  });
}

export function useSubmitApplicationScreeningAssessment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, assessment, idempotencyKey }: {
      applicationId: string;
      assessment: ApplicationScreeningAssessmentRequest;
      idempotencyKey: string;
    }) => submitApplicationScreeningAssessment(applicationId, assessment, idempotencyKey),
    onSuccess: async (_assessment, { applicationId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: applicationScreeningQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: [...applicationScreeningQueryKeys.all, "job-comparison"],
        }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
      ]);
    },
  });
}
