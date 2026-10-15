"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createHrisConnection,
  deleteHrisConnection,
  disableHrisConnection,
  listHrisConnections,
  listHrisHandoffs,
  retryHrisHandoff,
} from "../services/hris";
import type { CreateHrisConnectionRequest, HrisHandoffStatus } from "@/types/api/hris";

export const hrisQueryKeys = {
  all: ["hris"] as const,
  connections: () => [...hrisQueryKeys.all, "connections"] as const,
  handoffs: (status?: HrisHandoffStatus) => [...hrisQueryKeys.all, "handoffs", status] as const,
};

export function useHrisConnections(enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: hrisQueryKeys.connections(),
    queryFn: ({ signal }) => listHrisConnections({ signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useHrisHandoffs(statusFilter?: HrisHandoffStatus, cursor?: string, enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: [...hrisQueryKeys.handoffs(statusFilter), cursor],
    queryFn: ({ signal }) => listHrisHandoffs({ limit: 50, status: statusFilter, cursor }, { signal }),
    enabled: status === "authenticated" && enabled,
    refetchInterval: 15_000,
  });
}

export function useCreateHrisConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ request, idempotencyKey }: { request: CreateHrisConnectionRequest; idempotencyKey: string }) =>
      createHrisConnection(request, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: hrisQueryKeys.connections() });
    },
  });
}

export function useDisableHrisConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version, idempotencyKey }: { id: string; version: number; idempotencyKey: string }) =>
      disableHrisConnection(id, version, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: hrisQueryKeys.connections() });
    },
  });
}

export function useDeleteHrisConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version, idempotencyKey }: { id: string; version: number; idempotencyKey: string }) =>
      deleteHrisConnection(id, version, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: hrisQueryKeys.connections() });
    },
  });
}

export function useRetryHrisHandoff() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version, idempotencyKey }: { id: string; version: number; idempotencyKey: string }) =>
      retryHrisHandoff(id, version, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [...hrisQueryKeys.all, "handoffs"] });
    },
  });
}
