import { get, type RequestOptions } from "../client";
import type { NotificationActionItemsResponse } from "@/types/api";

export async function getNotificationActionItems(
  options?: RequestOptions,
): Promise<NotificationActionItemsResponse> {
  return get<NotificationActionItemsResponse>("/notifications/action-items", options);
}
