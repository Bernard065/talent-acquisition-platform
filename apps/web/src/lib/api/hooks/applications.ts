"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createApplication,
  assignApplication,
  completeApplicationFollowUp,
  createApplicationFollowUp,
  getApplicationActivity,
  getApplication,
  getApplicationPipelineSummary,
  listApplicationPipeline,
  listApplicationFollowUps,
  listApplications,
  transitionApplicationStage,
  updateApplicationFollowUp,
  type ApplicationFilterParams,
  type ApplicationSearchParams,
} from "../services/applications";
import type {
  ApplicationResponse,
  ApplicationAssignmentRequest,
  ApplicationFollowUpCompleteRequest,
  ApplicationFollowUpRequest,
  ApplicationFollowUpUpdateRequest,
  ApplicationCreateRequest,
  ApplicationRejectionReason,
  ApplicationStatus,
  ApplicationPipelineSummaryResponse,
} from "@/types/api/applications";

export const applicationQueryKeys = {
  all: ["applications"] as const,
  lists: () => [...applicationQueryKeys.all, "list"] as const,
  list: (params: ApplicationSearchParams = {}) =>
    [...applicationQueryKeys.lists(), params] as const,
  pipelines: () => [...applicationQueryKeys.all, "pipeline"] as const,
  pipeline: (params: ApplicationSearchParams = {}) =>
    [...applicationQueryKeys.pipelines(), params] as const,
  pipelineSummaries: () => [...applicationQueryKeys.all, "pipeline-summary"] as const,
  pipelineSummary: (params: ApplicationFilterParams = {}) =>
    [...applicationQueryKeys.pipelineSummaries(), params] as const,
  detail: (id: string) => [...applicationQueryKeys.all, "detail", id] as const,
  activity: (id: string) => [...applicationQueryKeys.all, "activity", id] as const,
  followUps: (id: string) => [...applicationQueryKeys.all, "follow-ups", id] as const,
};

export function useApplications(params: ApplicationSearchParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: applicationQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listApplications({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useApplicationPipeline(
  params: ApplicationSearchParams = {},
  enabled = true,
) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: applicationQueryKeys.pipeline(params),
    queryFn: ({ pageParam, signal }) =>
      listApplicationPipeline({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated" && enabled,
  });
}

export function useApplicationPipelineSummary(
  params: ApplicationFilterParams = {},
  enabled = true,
) {
  const { status } = useSession();

  return useQuery<ApplicationPipelineSummaryResponse>({
    queryKey: applicationQueryKeys.pipelineSummary(params),
    queryFn: ({ signal }) => getApplicationPipelineSummary(params, { signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useApplication(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: applicationQueryKeys.detail(id),
    queryFn: ({ signal }) => getApplication(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useApplicationActivity(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: applicationQueryKeys.activity(id),
    queryFn: ({ signal }) => getApplicationActivity(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useApplicationFollowUps(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: applicationQueryKeys.followUps(id),
    queryFn: ({ signal }) => listApplicationFollowUps(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

function useInvalidateFollowUps() {
  const queryClient = useQueryClient();
  return async (id: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: applicationQueryKeys.followUps(id) }),
      queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
      queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
    ]);
  };
}

export function useCreateApplicationFollowUp() {
  const invalidateFollowUps = useInvalidateFollowUps();
  return useMutation({
    mutationFn: ({ id, followUp, idempotencyKey }: {
      id: string;
      followUp: ApplicationFollowUpRequest;
      idempotencyKey: string;
    }) => createApplicationFollowUp(id, followUp, idempotencyKey),
    onSuccess: (_result, { id }) => invalidateFollowUps(id),
  });
}

export function useUpdateApplicationFollowUp() {
  const invalidateFollowUps = useInvalidateFollowUps();
  return useMutation({
    mutationFn: ({ id, followUpId, followUp, idempotencyKey }: {
      id: string;
      followUpId: string;
      followUp: ApplicationFollowUpUpdateRequest;
      idempotencyKey: string;
    }) => updateApplicationFollowUp(id, followUpId, followUp, idempotencyKey),
    onSuccess: (_result, { id }) => invalidateFollowUps(id),
  });
}

export function useCompleteApplicationFollowUp() {
  const invalidateFollowUps = useInvalidateFollowUps();
  return useMutation({
    mutationFn: ({ id, followUpId, followUp, idempotencyKey }: {
      id: string;
      followUpId: string;
      followUp: ApplicationFollowUpCompleteRequest;
      idempotencyKey: string;
    }) => completeApplicationFollowUp(id, followUpId, followUp, idempotencyKey),
    onSuccess: (_result, { id }) => invalidateFollowUps(id),
  });
}

export function useAssignApplication() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, assignment, idempotencyKey }: {
      id: string;
      assignment: ApplicationAssignmentRequest;
      idempotencyKey: string;
    }) => assignApplication(id, assignment, idempotencyKey),
    onSuccess: async (application) => {
      queryClient.setQueryData(
        applicationQueryKeys.detail(application.id),
        application,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
      ]);
    },
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ application, idempotencyKey }: {
      application: ApplicationCreateRequest;
      idempotencyKey: string;
    }) => createApplication(application, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
      ]);
    },
  });
}

export function useTransitionApplicationStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, targetStatus, expectedVersion, rejectionReason, idempotencyKey }: {
      id: string;
      targetStatus: ApplicationStatus;
      expectedVersion: number;
      rejectionReason?: ApplicationRejectionReason;
      idempotencyKey: string;
    }) =>
      transitionApplicationStage(
        id,
        {
          target_status: targetStatus,
          expected_version: expectedVersion,
          ...(rejectionReason ? { rejection_reason: rejectionReason } : {}),
        },
        idempotencyKey,
      ),
    onSuccess: async (application) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
        queryClient.invalidateQueries({
          queryKey: applicationQueryKeys.activity(application.id),
        }),
        queryClient.setQueryData(
          applicationQueryKeys.detail(application.id),
          application,
        ),
      ]);
    },
  });
}

export interface BulkApplicationStageTransition {
  id: string;
  expectedVersion: number;
  idempotencyKey: string;
}

export interface BulkApplicationStageTransitionResult {
  id: string;
  application?: ApplicationResponse;
  error?: unknown;
}

export function useBulkTransitionApplicationStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      transitions,
      targetStatus,
      rejectionReason,
    }: {
      transitions: BulkApplicationStageTransition[];
      targetStatus: ApplicationStatus;
      rejectionReason?: ApplicationRejectionReason;
    }): Promise<BulkApplicationStageTransitionResult[]> => {
      const results: BulkApplicationStageTransitionResult[] = new Array(transitions.length);
      let nextIndex = 0;
      const workerCount = Math.min(5, transitions.length);

      await Promise.all(Array.from({ length: workerCount }, async () => {
        while (nextIndex < transitions.length) {
          const index = nextIndex++;
          const transition = transitions[index];
          try {
            const application = await transitionApplicationStage(
              transition.id,
              {
                target_status: targetStatus,
                expected_version: transition.expectedVersion,
                ...(rejectionReason ? { rejection_reason: rejectionReason } : {}),
              },
              transition.idempotencyKey,
            );
            results[index] = { id: transition.id, application };
          } catch (error) {
            results[index] = { id: transition.id, error };
          }
        }
      }));

      return results;
    },
    onSuccess: async (results) => {
      for (const result of results) {
        if (result.application) {
          queryClient.setQueryData(
            applicationQueryKeys.detail(result.application.id),
            result.application,
          );
        }
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.pipelineSummaries() }),
      ]);
    },
  });
}
