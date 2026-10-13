import { get, put, type RequestOptions } from "../client";
import type {
  NotificationActionItemsResponse,
  NotificationPreference,
  NotificationPreferenceEventType,
  UpdateNotificationPreferenceRequest,
} from "@/types/api";

export async function getNotificationActionItems(
  options?: RequestOptions,
): Promise<NotificationActionItemsResponse> {
  return get<NotificationActionItemsResponse>("/notifications/action-items", options);
}

export async function getNotificationPreferences(
  options?: RequestOptions,
): Promise<NotificationPreference[]> {
  return get<NotificationPreference[]>("/notification-preferences", options);
}

export async function updateNotificationPreference(
  eventType: NotificationPreferenceEventType,
  body: UpdateNotificationPreferenceRequest,
  options: RequestOptions,
): Promise<NotificationPreference> {
  return put<NotificationPreference>(
    `/notification-preferences/${encodeURIComponent(eventType)}/email`,
    body,
    options,
  );
}
