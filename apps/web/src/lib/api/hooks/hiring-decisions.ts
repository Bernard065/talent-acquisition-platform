"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { applicationQueryKeys } from "./applications";
import { getApplicationHiringDecision, recordApplicationHiringDecision } from "../services/hiring-decisions";
import type { RecordHiringDecisionRequest } from "@/types/api/applications";

export const hiringDecisionQueryKeys = {
  all: ["hiring-decisions"] as const,
  state: (applicationId: string) => [...hiringDecisionQueryKeys.all, applicationId] as const,
};

export function useApplicationHiringDecision(applicationId: string, enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: hiringDecisionQueryKeys.state(applicationId),
    queryFn: ({ signal }) => getApplicationHiringDecision(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
  });
}

export function useRecordApplicationHiringDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, decision, idempotencyKey }: {
      applicationId: string;
      decision: RecordHiringDecisionRequest;
      idempotencyKey: string;
    }) => recordApplicationHiringDecision(applicationId, decision, idempotencyKey),
    onSuccess: async (_decision, { applicationId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: hiringDecisionQueryKeys.state(applicationId) }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.detail(applicationId) }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.activity(applicationId) }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
      ]);
    },
  });
}
