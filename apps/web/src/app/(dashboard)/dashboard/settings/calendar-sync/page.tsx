"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  useCalendarSyncOperations,
  useRetryCalendarSyncOperation,
} from "@/lib/api/hooks/calendar-sync-operations";
import type {
  CalendarSyncOperationItem,
  InterviewCalendarSyncStatus,
} from "@/types/api";

const PAGE_SIZE = 25;

const statusLabels: Record<InterviewCalendarSyncStatus, string> = {
  pending: "Pending",
  synced: "Synced",
  failed: "Failed",
  disabled: "Disconnected",
};

function deliveryLabel(item: CalendarSyncOperationItem): string {
  if (item.sync_status === "failed") return "Failed";
  if (item.sync_status === "synced") return "Synced";
  if (item.sync_status === "disabled" || item.connection_status === "disabled") {
    return "Disconnected";
  }
  if (item.outbox_status === "processing") return "Syncing";
  if (item.outbox_status === "pending") return "Queued";
  return statusLabels[item.sync_status];
}

function formatUtcDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return `${date.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

export default function CalendarSyncOperationsPage() {
  const [status, setStatus] = useState<InterviewCalendarSyncStatus | "all">("all");
  const [offset, setOffset] = useState(0);
  const query = useCalendarSyncOperations({
    limit: PAGE_SIZE,
    offset,
    ...(status === "all" ? {} : { status }),
  });
  const retry = useRetryCalendarSyncOperation();
  const page = query.data;
  const pageCount = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const retryActionShown = new Set<string>();

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <header>
        <Link href="/dashboard/settings" className="text-sm font-medium text-sr-green hover:underline">
          ← Settings
        </Link>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-sr-text-blue">
          Calendar sync
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          Monitor interview calendar delivery for your workspace and retry failed events.
        </p>
      </header>

      {page && (
        <section
          className={`rounded-xl border p-4 ${page.worker_available
            ? "border-green-200 bg-green-50 text-green-950"
            : "border-amber-200 bg-amber-50 text-amber-950"}`}
          aria-live="polite"
        >
          <p className="font-semibold">
            Calendar worker {page.worker_available ? "is available" : "is unavailable"}
          </p>
          <p className="mt-1 text-sm">
            Last heartbeat: {formatUtcDateTime(page.worker_last_seen_at)}
          </p>
        </section>
      )}

      <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-gray-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div>
            <h2 className="font-semibold text-sr-text-blue">Recent calendar deliveries</h2>
            {page && <p className="mt-1 text-sm text-gray-500">{page.total} delivery records</p>}
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <span>Status</span>
            <select
              value={status}
              onChange={(event) => {
                const next = event.currentTarget.value as InterviewCalendarSyncStatus | "all";
                setStatus(next);
                setOffset(0);
              }}
              className="h-10 rounded-lg border border-gray-300 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sr-green"
            >
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="synced">Synced</option>
              <option value="failed">Failed</option>
              <option value="disabled">Disconnected</option>
            </select>
          </label>
        </div>

        {query.isLoading ? (
          <p className="p-6 text-sm text-gray-600" role="status">Loading calendar deliveries…</p>
        ) : query.isError ? (
          <div className="p-6">
            <p className="text-sm text-red-800" role="alert">Couldn’t load calendar deliveries.</p>
            <Button className="mt-3" variant="outline" onClick={() => void query.refetch()}>
              Try again
            </Button>
          </div>
        ) : !page?.items.length ? (
          <p className="p-6 text-sm text-gray-600">
            No calendar delivery records match this filter.
          </p>
        ) : (
          <>
            {retry.isError && (
              <p className="mx-4 mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">
                The retry could not be queued. Refresh the list and try again.
              </p>
            )}
            {retry.isSuccess && (
              <p className="mx-4 mt-4 rounded-lg bg-green-50 p-3 text-sm text-green-800" role="status">
                Calendar retry queued.
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th className="px-5 py-3 font-medium">Interview</th>
                    <th className="px-5 py-3 font-medium">Calendar owner</th>
                    <th className="px-5 py-3 font-medium">Delivery</th>
                    <th className="px-5 py-3 font-medium">Attempts</th>
                    <th className="px-5 py-3 font-medium">Last attempt</th>
                    <th className="px-5 py-3 font-medium">Last error</th>
                    <th className="px-5 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {page.items.map((item) => {
                    const showRetry = item.can_retry && !retryActionShown.has(item.interview_session_id);
                    if (showRetry) retryActionShown.add(item.interview_session_id);
                    const isRetrying = retry.isPending
                      && retry.variables === item.interview_session_id;
                    return (
                      <tr key={item.id}>
                        <td className="px-5 py-4">
                          <Link
                            href={`/dashboard/interviews/${item.interview_session_id}`}
                            className="font-medium text-sr-text-blue hover:text-sr-green hover:underline"
                          >
                            {item.interview_title}
                          </Link>
                          <p className="mt-1 text-xs text-gray-500">
                            {formatUtcDateTime(item.scheduled_start_at)}
                          </p>
                        </td>
                        <td className="px-5 py-4">
                          <span className="font-medium text-gray-800">{item.calendar_owner_display_name}</span>
                          <span className="mt-1 block text-xs capitalize text-gray-500">{item.provider} calendar</span>
                        </td>
                        <td className="px-5 py-4">
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${item.sync_status === "failed"
                            ? "bg-red-50 text-red-700"
                            : item.sync_status === "synced"
                              ? "bg-green-50 text-green-700"
                              : "bg-gray-100 text-gray-700"}`}>
                            {deliveryLabel(item)}
                          </span>
                        </td>
                        <td className="px-5 py-4 tabular-nums text-gray-700">{item.attempts}</td>
                        <td className="px-5 py-4 text-gray-600">{formatUtcDateTime(item.last_attempt_at)}</td>
                        <td className="px-5 py-4 text-gray-600">
                          {item.last_error_code?.replaceAll("_", " ") ?? "—"}
                        </td>
                        <td className="px-5 py-4 text-right">
                          {showRetry ? (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={retry.isPending}
                              onClick={() => retry.mutate(item.interview_session_id)}
                            >
                              {isRetrying ? "Queueing…" : "Retry"}
                            </Button>
                          ) : (
                            <span className="text-xs text-gray-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <footer className="flex flex-col gap-3 border-t border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <p className="text-sm text-gray-500">Page {currentPage} of {pageCount}</p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= page.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
