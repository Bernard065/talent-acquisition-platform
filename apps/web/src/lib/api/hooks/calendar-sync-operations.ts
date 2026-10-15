"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  listCalendarSyncOperations,
  retryCalendarSyncOperation,
  type CalendarSyncOperationsParams,
} from "../services/calendar-sync-operations";
import { interviewQueryKeys } from "./interviews";

export const calendarSyncOperationsQueryKeys = {
  all: ["calendar-sync-operations"] as const,
  list: (params: CalendarSyncOperationsParams = {}) =>
    [...calendarSyncOperationsQueryKeys.all, params] as const,
};

export function useCalendarSyncOperations(
  params: CalendarSyncOperationsParams = {},
) {
  const { status } = useSession();

  return useQuery({
    queryKey: calendarSyncOperationsQueryKeys.list(params),
    queryFn: ({ signal }) => listCalendarSyncOperations(params, { signal }),
    enabled: status === "authenticated",
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (item) => item.outbox_status === "pending" || item.outbox_status === "processing",
      )
        ? 15_000
        : false,
  });
}

export function useRetryCalendarSyncOperation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (interviewSessionId: string) =>
      retryCalendarSyncOperation(interviewSessionId),
    onSuccess: async (_result, interviewSessionId) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: calendarSyncOperationsQueryKeys.all,
        }),
        queryClient.invalidateQueries({
          queryKey: interviewQueryKeys.calendarSyncs(interviewSessionId),
        }),
      ]);
    },
  });
}
