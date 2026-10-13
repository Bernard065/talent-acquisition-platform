"use client";

import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { getNotificationActionItems } from "../services/notifications";

export const notificationQueryKeys = {
  actionItems: ["notifications", "action-items"] as const,
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
