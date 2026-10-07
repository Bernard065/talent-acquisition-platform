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
  getApplication,
  listApplicationPipeline,
  listApplications,
  transitionApplicationStage,
  type ApplicationSearchParams,
} from "../services/applications";
import type {
  ApplicationCreateRequest,
  ApplicationRejectionReason,
  ApplicationStatus,
} from "@/types/api/applications";

export const applicationQueryKeys = {
  all: ["applications"] as const,
  lists: () => [...applicationQueryKeys.all, "list"] as const,
  list: (params: ApplicationSearchParams = {}) =>
    [...applicationQueryKeys.lists(), params] as const,
  pipelines: () => [...applicationQueryKeys.all, "pipeline"] as const,
  pipeline: (params: ApplicationSearchParams = {}) =>
    [...applicationQueryKeys.pipelines(), params] as const,
  detail: (id: string) => [...applicationQueryKeys.all, "detail", id] as const,
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

export function useApplicationPipeline(params: ApplicationSearchParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: applicationQueryKeys.pipeline(params),
    queryFn: ({ pageParam, signal }) =>
      listApplicationPipeline({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
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
        queryClient.setQueryData(
          applicationQueryKeys.detail(application.id),
          application,
        ),
      ]);
    },
  });
}
