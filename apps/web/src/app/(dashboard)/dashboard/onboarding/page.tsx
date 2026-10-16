"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { useOnboardingOverview } from "@/lib/api/hooks/onboarding";
import type { OnboardingInstanceStatus } from "@/types/api/onboarding";

type StatusFilter = "all" | OnboardingInstanceStatus;
const PAGE_SIZE = 25;

const statusLabels: Record<OnboardingInstanceStatus, string> = {
  active: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

function progressLabel(completed: number, total: number): string {
  return total === 0 ? "No tasks" : `${completed} of ${total} tasks`;
}

export default function OnboardingPage() {
  const { status: sessionStatus } = useSession();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({
    page,
    limit: PAGE_SIZE,
    query: query || undefined,
    status: statusFilter === "all" ? undefined : statusFilter,
    overdue_only: overdueOnly || undefined,
  }), [overdueOnly, page, query, statusFilter]);
  const overview = useOnboardingOverview(params);
  const items = useMemo(() => overview.data?.items ?? [], [overview.data?.items]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const isLoading = sessionStatus === "loading" || overview.isLoading;
  const total = overview.data?.total ?? 0;
  const activeCount = overview.data?.active_plan_count ?? 0;
  const overdueCount = overview.data?.overdue_task_count ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(query || statusFilter !== "all" || overdueOnly);

  return (
    <div className="mx-auto flex w-full max-w-375 flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Onboarding</h1>
        <p className="mt-1 text-sm text-gray-600">
          Track new-hire plans, task progress, and overdue work across your workspace.
        </p>
      </header>

      <section aria-label="Onboarding summary" className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-600">Active plans</p>
          <p className="mt-1 text-2xl font-semibold text-sr-text-blue">{isLoading ? "—" : activeCount}</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-600">Overdue tasks</p>
          <p className="mt-1 text-2xl font-semibold text-sr-text-blue">{isLoading ? "—" : overdueCount}</p>
        </div>
      </section>

      <section aria-label="Onboarding filters" className="grid gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Search new hires or roles
          <input
            type="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Name or job title"
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Plan status
          <select
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value as StatusFilter);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="active">In progress</option>
            <option value="all">All plans</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700 sm:col-span-2">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(event) => {
              setOverdueOnly(event.target.checked);
              setPage(1);
            }}
            className="h-4 w-4 rounded border-gray-300 text-sr-green focus:ring-sr-green"
          />
          Show plans with overdue tasks only
        </label>
      </section>

      <section aria-labelledby="onboarding-plans-heading" className="overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-5 py-4">
          <h2 id="onboarding-plans-heading" className="font-semibold text-sr-text-blue">Onboarding plans</h2>
          <p className="mt-1 text-sm text-gray-600">Open a hired application to update task owners and statuses.</p>
        </div>

        {isLoading ? (
          <p className="px-5 py-10 text-center text-sm text-gray-600" role="status">Loading onboarding plans…</p>
        ) : overview.isError ? (
          <div className="px-5 py-10 text-center">
            <p className="text-sm text-red-800" role="alert">We couldn’t load onboarding plans from your workspace.</p>
            <button type="button" onClick={() => void overview.refetch()} className="mt-3 text-sm font-medium text-sr-text-blue underline">Try again</button>
          </div>
        ) : items.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <h3 className="font-semibold text-sr-text-blue">{hasFilters ? "No plans match these filters" : "No onboarding plans yet"}</h3>
            <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600">
              {hasFilters
                ? "Change the search or status filter to see other plans."
                : "Start onboarding from a hired application after creating a reusable plan in Settings → Onboarding."}
            </p>
            {hasFilters && <button type="button" onClick={() => {
              setSearchInput("");
              setQuery("");
              setStatusFilter("all");
              setOverdueOnly(false);
              setPage(1);
            }} className="mt-4 text-sm font-medium text-sr-text-blue underline">Clear filters</button>}
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-100 md:hidden">
              {items.map((item) => (
                <article key={item.instance.id} className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link href={`/dashboard/applications/${item.instance.application_id}`} className="font-medium text-sr-text-blue hover:underline">
                        {item.employee_name}
                      </Link>
                      <p className="mt-0.5 text-sm text-gray-600">{item.job_title}</p>
                    </div>
                    <StatusBadge status={item.instance.status} />
                  </div>
                  <ProgressBar completed={item.completed_tasks} total={item.total_tasks} />
                  <div className="flex flex-wrap justify-between gap-2 text-xs text-gray-500">
                    <span>Started {formatDate(item.instance.started_at)}</span>
                    <span className={item.overdue_tasks ? "font-medium text-red-700" : ""}>
                      {item.overdue_tasks ? `${item.overdue_tasks} overdue` : "No overdue tasks"}
                    </span>
                  </div>
                </article>
              ))}
            </div>

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-190 text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50 text-xs font-medium uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-5 py-3">New hire</th>
                    <th scope="col" className="px-5 py-3">Progress</th>
                    <th scope="col" className="px-5 py-3">Overdue</th>
                    <th scope="col" className="px-5 py-3">Started</th>
                    <th scope="col" className="px-5 py-3">Status</th>
                    <th scope="col" className="px-5 py-3"><span className="sr-only">Open plan</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {items.map((item) => (
                    <tr key={item.instance.id} className="hover:bg-gray-50">
                      <td className="px-5 py-4">
                        <Link href={`/dashboard/applications/${item.instance.application_id}`} className="font-medium text-sr-text-blue hover:underline">{item.employee_name}</Link>
                        <p className="mt-0.5 text-xs text-gray-500">{item.job_title}</p>
                      </td>
                      <td className="w-56 px-5 py-4"><ProgressBar completed={item.completed_tasks} total={item.total_tasks} /></td>
                      <td className="px-5 py-4">{item.overdue_tasks ? <span className="font-medium text-red-700">{item.overdue_tasks}</span> : <span className="text-gray-500">—</span>}</td>
                      <td className="px-5 py-4 text-gray-700">{formatDate(item.instance.started_at)}</td>
                      <td className="px-5 py-4"><StatusBadge status={item.instance.status} /></td>
                      <td className="px-5 py-4 text-right"><Link href={`/dashboard/applications/${item.instance.application_id}`} className="font-medium text-sr-text-blue hover:underline">Open</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <footer className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p aria-live="polite" className="text-sm text-gray-600">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} plans
              </p>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button type="button" disabled={page <= 1 || isLoading} onClick={() => setPage((current) => current - 1)} className="h-9 rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50">Previous</button>
                <span className="px-1 text-sm text-gray-600">Page {page} of {pageCount}</span>
                <button type="button" disabled={page >= pageCount || isLoading} onClick={() => setPage((current) => current + 1)} className="h-9 rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50">Next</button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: OnboardingInstanceStatus }) {
  const style = status === "active" ? "bg-amber-50 text-amber-900"
    : status === "completed" ? "bg-emerald-50 text-emerald-800"
    : "bg-gray-100 text-gray-700";
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${style}`}>{statusLabels[status]}</span>;
}

function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const percent = total === 0 ? 0 : Math.round((completed / total) * 100);
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs text-gray-600">
        <span>{progressLabel(completed, total)}</span>
        <span>{percent}%</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-gray-100" role="progressbar" aria-label="Onboarding task progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="h-full rounded-full bg-sr-green" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
