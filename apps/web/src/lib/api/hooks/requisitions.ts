"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createRequisition,
  getRequisition,
  listRequisitions,
  transitionRequisition,
  updateRequisition,
} from "../services/requisitions";
import type { PaginationParams } from "../types";
import type {
  RequisitionCreateRequest,
  RequisitionTransitionRequest,
  RequisitionUpdateRequest,
} from "@/types/api/requisitions";

export const requisitionQueryKeys = {
  all: ["requisitions"] as const,
  lists: () => [...requisitionQueryKeys.all, "list"] as const,
  list: (params: PaginationParams = {}) =>
    [...requisitionQueryKeys.lists(), params] as const,
  detail: (id: string) => [...requisitionQueryKeys.all, "detail", id] as const,
};

export function useRequisitions(params: PaginationParams = {}) {
  const { status } = useSession();

  return useInfiniteQuery({
    queryKey: requisitionQueryKeys.list(params),
    queryFn: ({ pageParam, signal }) =>
      listRequisitions({ ...params, cursor: pageParam }, { signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: status === "authenticated",
  });
}

export function useRequisition(id: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: requisitionQueryKeys.detail(id),
    queryFn: ({ signal }) => getRequisition(id, { signal }),
    enabled: status === "authenticated" && Boolean(id),
  });
}

export function useCreateRequisition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ requisition, idempotencyKey }: {
      requisition: RequisitionCreateRequest;
      idempotencyKey: string;
    }) => createRequisition(requisition, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: requisitionQueryKeys.lists() });
    },
  });
}

export function useUpdateRequisition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, requisition, idempotencyKey }: {
      id: string;
      requisition: RequisitionUpdateRequest;
      idempotencyKey: string;
    }) => updateRequisition(id, requisition, idempotencyKey),
    onSuccess: async (requisition) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: requisitionQueryKeys.lists() }),
        queryClient.setQueryData(
          requisitionQueryKeys.detail(requisition.id),
          requisition,
        ),
      ]);
    },
  });
}

export function useTransitionRequisition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, transition, idempotencyKey }: {
      id: string;
      transition: RequisitionTransitionRequest;
      idempotencyKey: string;
    }) => transitionRequisition(id, transition, idempotencyKey),
    onSuccess: async (requisition) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: requisitionQueryKeys.lists() }),
        queryClient.setQueryData(
          requisitionQueryKeys.detail(requisition.id),
          requisition,
        ),
      ]);
    },
  });
}
