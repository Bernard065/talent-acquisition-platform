"use client";

import { useState, type FormEvent } from "react";
import { RefreshCw, Search, X } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import { useAuditEvents } from "@/lib/api/hooks/audit-events";
import type { AuditEventSearchParams } from "@/types/api/audit-events";

const PAGE_SIZE = 50;

function formatAction(action: string): string {
  return action
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTimestamp(timestamp: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

export function AuditLogTab() {
  const [draft, setDraft] = useState({
    action: "",
    entity_type: "",
    actor: "",
    occurred_from: "",
    occurred_to: "",
  });
  const [filters, setFilters] = useState<AuditEventSearchParams>({
    limit: PAGE_SIZE,
    offset: 0,
  });
  const eventsQuery = useAuditEvents(filters);
  const events = eventsQuery.data?.items ?? [];
  const total = eventsQuery.data?.total ?? 0;
  const offset = eventsQuery.data?.offset ?? 0;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      action: draft.action.trim() || undefined,
      entity_type: draft.entity_type.trim() || undefined,
      actor: draft.actor.trim() || undefined,
      occurred_from: draft.occurred_from || undefined,
      occurred_to: draft.occurred_to || undefined,
      limit: PAGE_SIZE,
      offset: 0,
    });
  }

  function clearFilters() {
    setDraft({
      action: "",
      entity_type: "",
      actor: "",
      occurred_from: "",
      occurred_to: "",
    });
    setFilters({ limit: PAGE_SIZE, offset: 0 });
  }

  const errorMessage = eventsQuery.error instanceof ApiError
    ? eventsQuery.error.detail
    : "The audit history could not be loaded. Try again.";

  return (
    <section className="flex w-full flex-col gap-5">
      <header>
        <h2 className="text-lg font-semibold text-sr-text-blue">Workspace audit log</h2>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Review workspace activity with the actor, action, affected record, and request ID.
          Audit details are limited to protect candidate and employee information.
        </p>
      </header>

      <form
        onSubmit={applyFilters}
        className="grid gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:grid-cols-2 xl:grid-cols-5"
      >
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          Action
          <input
            value={draft.action}
            onChange={(event) => setDraft({ ...draft, action: event.target.value })}
            placeholder="e.g. application.stage_changed"
            maxLength={100}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          Record type
          <input
            value={draft.entity_type}
            onChange={(event) => setDraft({ ...draft, entity_type: event.target.value })}
            placeholder="e.g. application"
            maxLength={100}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          Actor
          <input
            value={draft.actor}
            onChange={(event) => setDraft({ ...draft, actor: event.target.value })}
            placeholder="Name or actor ID"
            maxLength={255}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          From
          <input
            type="date"
            value={draft.occurred_from}
            onChange={(event) => setDraft({ ...draft, occurred_from: event.target.value })}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          To
          <input
            type="date"
            value={draft.occurred_to}
            onChange={(event) => setDraft({ ...draft, occurred_to: event.target.value })}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2 xl:col-span-5">
          <button
            type="submit"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:bg-slate-800"
          >
            <Search aria-hidden="true" className="h-4 w-4" />
            Apply filters
          </button>
          <button
            type="button"
            onClick={clearFilters}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-gray-200 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <X aria-hidden="true" className="h-4 w-4" />
            Clear
          </button>
          <p className="text-sm text-gray-500 sm:ml-auto">
            {eventsQuery.isFetching ? "Updating…" : `${total.toLocaleString()} events`}
          </p>
        </div>
      </form>

      {eventsQuery.isError ? (
        <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5">
          <p className="text-sm text-red-800">{errorMessage}</p>
          <button
            type="button"
            onClick={() => void eventsQuery.refetch()}
            className="mt-3 inline-flex h-9 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-sm font-semibold text-red-800 hover:bg-red-100"
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" /> Retry
          </button>
        </section>
      ) : eventsQuery.isLoading ? (
        <p role="status" className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600">
          Loading workspace activity…
        </p>
      ) : events.length === 0 ? (
        <section className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
          <h3 className="font-semibold text-gray-900">No audit events found</h3>
          <p className="mt-2 text-sm text-gray-600">
            Try changing the filters or check again after workspace activity has been recorded.
          </p>
        </section>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">When</th>
                  <th className="px-4 py-3 font-semibold">Actor</th>
                  <th className="px-4 py-3 font-semibold">Action</th>
                  <th className="px-4 py-3 font-semibold">Record</th>
                  <th className="px-4 py-3 font-semibold">Request ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {events.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-gray-50/70">
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {formatTimestamp(item.occurred_at)}
                    </td>
                    <td className="max-w-56 px-4 py-3">
                      <span className="block truncate font-medium text-gray-900">
                        {item.actor_display_name ?? "System or removed user"}
                      </span>
                      {item.actor_subject && (
                        <span className="mt-0.5 block truncate font-mono text-xs text-gray-500">
                          {item.actor_subject}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {formatAction(item.action)}
                    </td>
                    <td className="max-w-64 px-4 py-3">
                      <span className="block font-medium text-gray-800">{item.entity_type}</span>
                      <span className="mt-0.5 block truncate font-mono text-xs text-gray-500">
                        {item.entity_id}
                      </span>
                    </td>
                    <td className="max-w-56 px-4 py-3 font-mono text-xs text-gray-500">
                      <span className="block truncate" title={item.request_id}>{item.request_id}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="flex flex-col gap-3 border-t border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-gray-500">
              Showing {offset + 1}–{Math.min(offset + events.length, total)} of {total.toLocaleString()}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0 || eventsQuery.isFetching}
                onClick={() => setFilters((current) => ({ ...current, offset: Math.max(0, offset - PAGE_SIZE) }))}
                className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={offset + events.length >= total || eventsQuery.isFetching}
                onClick={() => setFilters((current) => ({ ...current, offset: offset + PAGE_SIZE }))}
                className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </footer>
        </div>
      )}
    </section>
  );
}
