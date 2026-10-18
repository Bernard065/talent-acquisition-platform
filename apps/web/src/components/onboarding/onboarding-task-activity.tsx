"use client";

import { useState } from "react";
import { useOnboardingTaskActivity } from "@/lib/api/hooks/onboarding";
import type {
  OnboardingTaskEventType,
  OnboardingTaskStatus,
} from "@/types/api/onboarding";

const statusLabels: Record<OnboardingTaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Needs help",
  cancelled: "Cancelled",
};

function eventTitle(
  eventType: OnboardingTaskEventType,
  actorDisplayName: string,
  viewer: "employee" | "workspace",
): string {
  switch (eventType) {
    case "created":
      return "Task added to plan";
    case "assigned":
      return "Task assignment updated";
    case "due_date_changed":
      return "Due date changed";
    case "status_changed":
      return "Task status updated";
    case "completed":
      return "Task completed";
    case "blocked":
      return viewer === "employee" && actorDisplayName === "You"
        ? "Help requested"
        : "Task blocked";
    case "cancelled":
      return "Task cancelled";
  }
}

function formatOccurredAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

export function OnboardingTaskActivity({
  taskId,
  viewer,
}: {
  taskId: string;
  viewer: "employee" | "workspace";
}) {
  const [expanded, setExpanded] = useState(false);
  const activity = useOnboardingTaskActivity(taskId, expanded);

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
        className="text-sm font-medium text-sr-text-blue underline decoration-transparent underline-offset-2 hover:decoration-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sr-green"
      >
        {expanded ? "Hide activity" : "View task activity"}
      </button>

      {expanded && (
        <div className="mt-3" aria-live="polite">
          {activity.isLoading ? (
            <p className="text-sm text-gray-600" role="status">
              Loading task activity…
            </p>
          ) : activity.isError ? (
            <div className="flex flex-wrap items-center gap-2 text-sm text-red-800" role="alert">
              <span>We couldn’t load this task’s activity.</span>
              <button
                type="button"
                onClick={() => void activity.refetch()}
                disabled={activity.isFetching}
                className="font-medium underline disabled:cursor-not-allowed disabled:opacity-60"
              >
                {activity.isFetching ? "Retrying…" : "Try again"}
              </button>
            </div>
          ) : !activity.data?.items.length ? (
            <p className="text-sm text-gray-600">No activity has been recorded yet.</p>
          ) : (
            <ol className="ml-1 border-l border-gray-200 pl-4">
              {activity.data.items.map((item) => {
                const hasStatusChange = item.from_status !== item.to_status;
                let noteLabel = "Note";
                if (item.event_type === "blocked") {
                  noteLabel =
                    viewer === "employee" && item.actor_display_name === "You"
                      ? "Help request"
                      : "Reason";
                } else if (
                  item.from_status === "blocked" &&
                  item.to_status === "in_progress"
                ) {
                  noteLabel = "People Operations response";
                } else if (item.event_type === "assigned") {
                  noteLabel = "Assignment";
                } else if (item.event_type === "due_date_changed") {
                  noteLabel = "Due date";
                }

                return (
                  <li
                    key={item.id}
                    className="relative pb-4 last:pb-0"
                  >
                    <span
                      aria-hidden="true"
                      className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-sr-text-blue ring-1 ring-gray-300"
                    />
                    <div className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-2">
                      <p className="text-sm font-medium text-gray-900">
                        {eventTitle(item.event_type, item.actor_display_name, viewer)}
                      </p>
                      <p className="text-xs text-gray-500">
                        {item.actor_display_name} · {formatOccurredAt(item.occurred_at)}
                      </p>
                    </div>
                    {hasStatusChange && (
                      <p className="mt-1 text-sm text-gray-700">
                        {item.from_status
                          ? statusLabels[item.from_status]
                          : "Created"} {"→ "}
                        {statusLabels[item.to_status]}
                      </p>
                    )}
                    {item.note && (
                      <div className="mt-2 rounded-md bg-gray-50 p-3">
                        <p className="text-xs font-semibold text-gray-600">
                          {noteLabel}
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-sm text-gray-800">
                          {item.note}
                        </p>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
