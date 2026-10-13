"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  getNotificationActionItems,
  getNotificationPreferences,
  updateNotificationPreference,
} from "../services/notifications";
import type {
  NotificationPreference,
  NotificationPreferenceEventType,
} from "@/types/api";

export const notificationQueryKeys = {
  actionItems: ["notifications", "action-items"] as const,
  preferences: ["notifications", "preferences"] as const,
};

export function useNotificationActionItems() {
  const { status } = useSession();
  return useQuery({
    queryKey: notificationQueryKeys.actionItems,
    queryFn: ({ signal }) => getNotificationActionItems({ signal }),
    enabled: status === "authenticated",
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}

export function useNotificationPreferences() {
  const { status } = useSession();
  return useQuery({
    queryKey: notificationQueryKeys.preferences,
    queryFn: ({ signal }) => getNotificationPreferences({ signal }),
    enabled: status === "authenticated",
  });
}

export function useUpdateNotificationPreference() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      eventType,
      enabled,
      frequency,
      expectedVersion,
    }: {
      eventType: NotificationPreferenceEventType;
      enabled: boolean;
      frequency: "daily" | "weekly";
      expectedVersion: number;
    }) =>
      updateNotificationPreference(
        eventType,
        {
          enabled,
          digest_frequency: frequency,
          expected_version: expectedVersion,
        },
        { idempotencyKey: crypto.randomUUID() },
      ),
    onSuccess: (updatedPreference) => {
      queryClient.setQueryData<NotificationPreference[]>(
        notificationQueryKeys.preferences,
        (current) =>
          current?.map((preference) =>
            preference.event_type === updatedPreference.event_type &&
            preference.channel === updatedPreference.channel
              ? updatedPreference
              : preference,
          ),
      );
    },
    onError: () =>
      queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.preferences,
      }),
  });
}
