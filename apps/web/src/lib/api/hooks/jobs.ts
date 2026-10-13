"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createJobPostingFromRequisition,
  getJobPosting,
  listJobPostings,
  publishJobPosting,
  unpublishJobPosting,
  getJobApplicationQuestions,
  replaceJobApplicationQuestions,
  getJobScreeningRubric,
  replaceJobScreeningRubric,
} from "../services/jobs";
import type { PaginationParams } from "../types";
import type {
  CreateJobPostingRequest,
  ExpectedJobPostingVersionRequest,
  ReplaceJobApplicationQuestionsRequest,
} from "@/types/api/jobs";
import type { ReplaceScreeningRubricRequest } from "@/types/api/applications";

export const jobQueryKeys = {
  all: ["job-postings"] as const,
  lists: () => [...jobQueryKeys.all, "list"] as const,
  list: (params: PaginationParams = {}) => [...jobQueryKeys.lists(), params] as const,
  detail: (id: string) => [...jobQueryKeys.all, "detail", id] as const,
  applicationQuestions: (id: string) => [...jobQueryKeys.all, "application-questions", id] as const,
  screeningRubric: (id: string) => [...jobQueryKeys.all, "screening-rubric", id] as const,
};

export function useJobApplicationQuestions(id: string) {
  const { status } = useSession();
  return useQuery({
    queryKey: jobQueryKeys.applicationQuestions(id),
    queryFn: ({ signal }) => getJobApplicationQuestions(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useReplaceJobApplicationQuestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request, idempotencyKey }: {
      id: string;
      request: ReplaceJobApplicationQuestionsRequest;
      idempotencyKey: string;
    }) => replaceJobApplicationQuestions(id, request, idempotencyKey),
    onSuccess: async (result, { id }) => {
      queryClient.setQueryData(jobQueryKeys.applicationQuestions(id), result);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.detail(id) }),
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() }),
      ]);
    },
    onError: async (_error, { id }) => {
      await queryClient.invalidateQueries({ queryKey: jobQueryKeys.applicationQuestions(id) });
    },
  });
}

export function useJobScreeningRubric(id: string) {
  const { status } = useSession();
  return useQuery({
    queryKey: jobQueryKeys.screeningRubric(id),
    queryFn: ({ signal }) => getJobScreeningRubric(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useReplaceJobScreeningRubric() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, request, idempotencyKey }: {
      id: string;
      request: ReplaceScreeningRubricRequest;
      idempotencyKey: string;
    }) => replaceJobScreeningRubric(id, request, idempotencyKey),
    onSuccess: async (result, { id }) => {
      queryClient.setQueryData(jobQueryKeys.screeningRubric(id), result);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.detail(id) }),
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() }),
        queryClient.invalidateQueries({
          queryKey: ["application-screening-assessments", "job-comparison"],
        }),
      ]);
    },
    onError: async (_error, { id }) => {
      await queryClient.invalidateQueries({ queryKey: jobQueryKeys.screeningRubric(id) });
    },
  });
}

export function useJobPostings(params: PaginationParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: jobQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listJobPostings({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useJobPosting(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: jobQueryKeys.detail(id),
    queryFn: ({ signal }) => getJobPosting(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useCreateJobPostingFromRequisition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ requisitionId, request, idempotencyKey }: {
      requisitionId: string;
      request: CreateJobPostingRequest;
      idempotencyKey: string;
    }) => createJobPostingFromRequisition(requisitionId, request, idempotencyKey),
    onSuccess: async (posting) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() }),
        queryClient.setQueryData(jobQueryKeys.detail(posting.id), posting),
      ]);
    },
  });
}

export function usePublishJobPosting() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, request, idempotencyKey }: {
      id: string;
      request: ExpectedJobPostingVersionRequest;
      idempotencyKey: string;
    }) => publishJobPosting(id, request, idempotencyKey),
    onSuccess: async (posting) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() }),
        queryClient.setQueryData(jobQueryKeys.detail(posting.id), posting),
      ]);
    },
  });
}

export function useUnpublishJobPosting() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, request, idempotencyKey }: {
      id: string;
      request: ExpectedJobPostingVersionRequest;
      idempotencyKey: string;
    }) => unpublishJobPosting(id, request, idempotencyKey),
    onSuccess: async (posting) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() }),
        queryClient.setQueryData(jobQueryKeys.detail(posting.id), posting),
      ]);
    },
  });
}
