export interface StatCardData {
  label: string;
  value: string;
  change: string;
  changeNote: string;
  changeType: "positive" | "negative";
  isDown?: boolean;
  icon: React.ReactNode;
}

export interface ActivityItem {
  id: string;
  text: string;
  time: string;
  dotColor: string;
  dotRing: string;
}

export interface InterviewItem {
  id: string;
  initials: string;
  name: string;
  role: string;
  datetime: string;
  type: "Technical" | "Culture Fit" | "Final Round";
  avatarBg: string;
  badgeStyle: string;
}

export type SettingsTab = "profile" | "integrations" | "notifications";

export interface IntegrationItem {
  id: string;
  name: string;
  description: string;
  connected: boolean;
  category: string;
}

export interface NotificationItem {
  id: string;
  title: string;
  description: string;
  enabled: boolean;
}
