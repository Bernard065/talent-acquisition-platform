"use client";

import Link from "next/link";
import { ClipboardCheck, Clock3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNotificationActionItems } from "@/lib/api/hooks/notifications";

function formatDueAt(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function ActionNotifications() {
  const query = useNotificationActionItems();
  const items = query.data?.items ?? [];

  if (query.isLoading && !query.data) {
    return (
      <section className="rounded-xl border border-gray-200 bg-white p-5" aria-live="polite">
        <p className="text-sm text-gray-500">Checking for items that need your attention…</p>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5" role="status">
        <p className="text-sm text-amber-900">Reminders are temporarily unavailable.</p>
        <Button className="mt-3" variant="outline" size="sm" onClick={() => void query.refetch()}>
          Retry
        </Button>
      </section>
    );
  }

  if (!items.length) return null;

  return (
    <section aria-labelledby="action-notifications-heading" className="rounded-xl border border-amber-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-100 bg-amber-50/70 px-5 py-4 sm:px-6">
        <div>
          <h2 id="action-notifications-heading" className="text-lg font-semibold text-sr-text-blue">
            Needs your attention
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            Follow-ups and interview feedback remain here until completed.
          </p>
        </div>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-amber-900 ring-1 ring-amber-200">
          {items.length} {items.length === 1 ? "item" : "items"}
        </span>
      </div>

      <ul className="divide-y divide-gray-100">
        {items.map((item) => {
          const isFollowUp = item.kind === "overdue_follow_up";
          const Icon = isFollowUp ? Clock3 : ClipboardCheck;
          return (
            <li key={item.id}>
              <Link
                href={item.href}
                className="flex min-w-0 flex-col gap-3 px-5 py-4 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sr-green sm:flex-row sm:items-center sm:px-6"
              >
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${isFollowUp ? "bg-amber-100 text-amber-800" : "bg-blue-100 text-blue-800"}`}>
                  <Icon aria-hidden="true" className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-gray-900">
                    {isFollowUp ? `Overdue: ${item.title}` : item.title}
                  </span>
                  <span className="mt-1 block truncate text-sm text-gray-600">
                    {item.candidate_name} · {item.requisition_title}
                  </span>
                  <span className="mt-1 block text-xs text-gray-500">
                    {isFollowUp ? "Due" : "Interview ended"} {formatDueAt(item.due_at)} UTC
                  </span>
                </span>
                <span className="shrink-0 text-sm font-semibold text-sr-green">
                  {isFollowUp ? "Open application" : "Open interview"} →
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
