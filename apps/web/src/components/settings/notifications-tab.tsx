"use client";

import {
  useNotificationPreferences,
  useUpdateNotificationPreference,
} from "@/lib/api/hooks/notifications";
import type { NotificationPreferenceEventType } from "@/types/api";

const digestPreferences: Array<{
  eventType: NotificationPreferenceEventType;
  title: string;
  description: string;
}> = [
  {
    eventType: "action_item.overdue_follow_up_digest",
    title: "Overdue candidate follow-ups",
    description: "Include follow-ups that are past due for applications assigned to you.",
  },
  {
    eventType: "action_item.pending_interview_feedback_digest",
    title: "Pending interview feedback",
    description: "Include feedback you still need to submit after an interview.",
  },
];

export function NotificationsTab() {
  const query = useNotificationPreferences();
  const updatePreference = useUpdateNotificationPreference();

  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="border-b border-gray-100 p-6">
        <h2 className="text-lg font-bold text-sr-text-blue">Email digest preferences</h2>
        <p className="mt-1 text-sm text-gray-600">
          Choose which recruiting actions you receive and how often. Digests are sent only when enabled categories have items that need your attention; the delivery time is configured by your workspace administrator.
        </p>
      </header>

      {query.isLoading ? (
        <p className="p-6 text-sm text-gray-600" role="status">Loading notification preferences…</p>
      ) : query.isError && !query.data ? (
        <div className="p-6">
          <p className="text-sm text-red-800" role="alert">Notification preferences couldn’t be loaded.</p>
          <button
            type="button"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
            className="mt-3 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {query.isFetching ? "Retrying…" : "Try again"}
          </button>
        </div>
      ) : (
        <>
          {query.isError && (
            <p className="mx-6 mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
              Couldn’t refresh your preferences. Showing the last loaded settings.
            </p>
          )}

          <div className="divide-y divide-gray-100">
            {digestPreferences.map(({ eventType, title, description }) => {
              const preference = query.data?.find(
                (item) => item.event_type === eventType && item.channel === "email",
              );
              const isSaving =
                updatePreference.isPending &&
                updatePreference.variables?.eventType === eventType;

              return (
                <div
                  key={eventType}
                  className="flex flex-col justify-between gap-4 p-6 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
                    <p className="mt-1 text-sm text-gray-600">{description}</p>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-3">
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <span className="sr-only">Delivery frequency for {title}</span>
                      <select
                        aria-label={"Delivery frequency for " + title}
                        value={preference?.digest_frequency ?? "daily"}
                        disabled={!preference?.enabled || updatePreference.isPending}
                        onChange={(event) => {
                          if (!preference) return;
                          updatePreference.mutate({
                            eventType,
                            enabled: preference.enabled,
                            frequency: event.currentTarget.value === "weekly" ? "weekly" : "daily",
                            expectedVersion: preference.version,
                          });
                        }}
                        className="h-9 rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sr-green disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
                      >
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      role="switch"
                      aria-label={title}
                      aria-checked={preference?.enabled ?? false}
                      disabled={!preference || updatePreference.isPending}
                      onClick={() => {
                        if (!preference) return;
                        updatePreference.mutate({
                          eventType,
                          enabled: !preference.enabled,
                          frequency: preference.digest_frequency,
                          expectedVersion: preference.version,
                        });
                      }}
                      className={
                        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sr-green focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 " +
                        (preference?.enabled ? "bg-sr-green" : "bg-gray-300")
                      }
                    >
                      <span
                        aria-hidden="true"
                        className={
                          "inline-block size-5 rounded-full bg-white shadow transition-transform " +
                          (preference?.enabled ? "translate-x-5" : "translate-x-0.5")
                        }
                      />
                    </button>
                    {isSaving && <span className="text-xs text-gray-600" role="status">Saving…</span>}
                  </div>
                </div>
              );
            })}
          </div>

          {updatePreference.isError && (
            <p className="border-t border-red-100 bg-red-50 px-6 py-3 text-sm text-red-800" role="alert">
              Your preference couldn’t be saved. Refresh the settings and try again.
            </p>
          )}
          {updatePreference.isSuccess && (
            <p className="border-t border-green-100 bg-green-50 px-6 py-3 text-sm text-green-800" role="status">
              Notification preference saved.
            </p>
          )}
        </>
      )}
    </section>
  );
}
