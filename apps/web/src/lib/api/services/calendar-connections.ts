import { get, post, type RequestOptions } from "../client";
import type {
  CalendarAuthorizationUrlResponse,
  CalendarConnectionResponse,
  CalendarProvider,
} from "@/types/api";

export function listCalendarConnections(
  options?: RequestOptions,
): Promise<CalendarConnectionResponse[]> {
  return get<CalendarConnectionResponse[]>("/calendar-connections", options);
}

export function beginCalendarAuthorization(
  provider: CalendarProvider,
  options?: RequestOptions,
): Promise<CalendarAuthorizationUrlResponse> {
  return post<CalendarAuthorizationUrlResponse>(
    `/calendar-connections/${provider}/authorization`,
    undefined,
    options,
  );
}
