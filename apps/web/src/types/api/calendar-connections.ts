export type CalendarProvider = "google" | "microsoft";
export type CalendarConnectionStatus = "active" | "disabled";

export interface CalendarConnectionResponse {
  id: string;
  provider: CalendarProvider;
  status: CalendarConnectionStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CalendarAuthorizationUrlResponse {
  authorization_url: string;
  expires_in_seconds: number;
}
