"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { beginCalendarAuthorization, listCalendarConnections } from "../services/calendar-connections";
import type { CalendarProvider } from "@/types/api";

export const calendarConnectionQueryKeys = {
  all: ["calendar-connections"] as const,
  list: () => [...calendarConnectionQueryKeys.all, "list"] as const,
};

export function useCalendarConnections() {
  const { status } = useSession();

  return useQuery({
    queryKey: calendarConnectionQueryKeys.list(),
    queryFn: ({ signal }) => listCalendarConnections({ signal }),
    enabled: status === "authenticated",
  });
}

export function useBeginCalendarAuthorization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (provider: CalendarProvider) => beginCalendarAuthorization(provider),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: calendarConnectionQueryKeys.list() });
    },
  });
}
