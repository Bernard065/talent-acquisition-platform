"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createCandidate,
  getCandidate,
  getCandidateFilterOptions,
  listCandidates,
  requestCandidateErasure,
  type CandidateSearchParams,
} from "../services/candidates";
import type { CandidateCreateRequest } from "@/types/api";

export const candidateQueryKeys = {
  all: ["candidates"] as const,
  lists: () => [...candidateQueryKeys.all, "list"] as const,
  list: (params: CandidateSearchParams = {}) =>
    [...candidateQueryKeys.lists(), params] as const,
  filterOptions: () => [...candidateQueryKeys.all, "filter-options"] as const,
  detail: (id: string) => [...candidateQueryKeys.all, "detail", id] as const,
};

export function useCandidates(params: CandidateSearchParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: candidateQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listCandidates(
        { ...params, cursor: pageParam },
        { signal },
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useCandidateFilterOptions() {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateQueryKeys.filterOptions(),
    queryFn: ({ signal }) => getCandidateFilterOptions({ signal }),
    enabled: status === "authenticated",
  });
}

export function useCandidate(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateQueryKeys.detail(id),
    queryFn: ({ signal }) => getCandidate(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useCreateCandidate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      candidate,
      idempotencyKey,
    }: {
      candidate: CandidateCreateRequest;
      idempotencyKey: string;
    }) => createCandidate(candidate, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.filterOptions() }),
      ]);
    },
  });
}

export function useRequestCandidateErasure() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      idempotencyKey,
    }: {
      id: string;
      idempotencyKey: string;
    }) => requestCandidateErasure(id, idempotencyKey),
    onSuccess: async (_result, { id }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.detail(id) }),
        queryClient.invalidateQueries({ queryKey: candidateQueryKeys.filterOptions() }),
      ]);
    },
  });
}
