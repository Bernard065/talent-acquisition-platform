export type NotificationActionItemKind =
  | "overdue_follow_up"
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
