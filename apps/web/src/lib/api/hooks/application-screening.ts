"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  listApplicationScreeningAssessments,
  submitApplicationScreeningAssessment,
} from "../services/application-screening";
import type { ApplicationScreeningAssessmentRequest } from "@/types/api";

export const applicationScreeningQueryKeys = {
  all: ["application-screening-assessments"] as const,
  application: (applicationId: string) =>
    [...applicationScreeningQueryKeys.all, applicationId] as const,
};

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
      await queryClient.invalidateQueries({
        queryKey: applicationScreeningQueryKeys.application(applicationId),
      });
    },
  });
}
