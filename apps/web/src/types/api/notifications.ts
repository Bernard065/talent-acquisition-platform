export type NotificationActionItemKind =
  | "overdue_follow_up"
  | "overdue_onboarding_task"
  | "pending_interview_feedback";

export interface NotificationActionItem {
  id: string;
  kind: NotificationActionItemKind;
  title: string;
  candidate_name: string;
  requisition_title: string;
  due_at: string;
  href: string;
  application_id: string;
}

export interface NotificationActionItemsResponse {
  items: NotificationActionItem[];
}

export type NotificationPreferenceEventType =
  | "action_item.overdue_follow_up_digest"
  | "action_item.overdue_onboarding_task_digest"
  | "action_item.pending_interview_feedback_digest"
  | "interview.calendar_sync_failed";

export interface NotificationPreference {
  event_type: string;
  channel: "email";
  enabled: boolean;
  digest_frequency: "daily" | "weekly";
  version: number;
  updated_at: string | null;
}

export interface UpdateNotificationPreferenceRequest {
  enabled: boolean;
  digest_frequency: "daily" | "weekly";
  expected_version: number;
}
