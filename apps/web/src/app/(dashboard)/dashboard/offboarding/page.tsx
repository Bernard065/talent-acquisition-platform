"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { useEmployeeOffboardingOverview } from "@/lib/api/hooks/employee-records";
import type {
  EmployeeOffboardingOverviewItemResponse,
  EmployeeOffboardingTaskStatus,
} from "@/types/api/employee-records";

const PAGE_SIZE = 25;

const taskStatuses: { value: EmployeeOffboardingTaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" },
  { value: "completed", label: "Completed" },
];

function formatDate(value: string | null): string {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function progressPercent(item: EmployeeOffboardingOverviewItemResponse): number {
  return item.total_task_count === 0
    ? 0
    : Math.round((item.completed_task_count / item.total_task_count) * 100);
}

function CaseProgress({ item }: { item: EmployeeOffboardingOverviewItemResponse }) {
  const percent = progressPercent(item);
  return (
    <div className="min-w-36">
      <div className="flex items-center justify-between gap-3 text-xs text-gray-600">
        <span>{item.completed_task_count} of {item.total_task_count} tasks</span>
        <span>{percent}%</span>
      </div>
      <div
        className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100"
        role="progressbar"
        aria-label={`Checklist progress for ${item.employee_name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div className="h-full rounded-full bg-sr-green" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function EmployeeLink({ item }: { item: EmployeeOffboardingOverviewItemResponse }) {
  return (
    <Link
      href={`/dashboard/applications/${item.application_id}`}
      className="font-semibold text-sr-text-blue hover:underline focus-visible:rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-sr-green"
    >
      {item.employee_name}
    </Link>
  );
}

export default function OffboardingPage() {
  const { status: sessionStatus } = useSession();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [taskStatus, setTaskStatus] = useState<EmployeeOffboardingTaskStatus | "">("");
  const [dueFrom, setDueFrom] = useState("");
  const [dueTo, setDueTo] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [page, setPage] = useState(1);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
  }, []);

  const invalidDateRange = Boolean(dueFrom && dueTo && dueFrom > dueTo);
  const overviewQuery = useEmployeeOffboardingOverview({
    page,
    limit: PAGE_SIZE,
    query: query || undefined,
    task_status: taskStatus || undefined,
    due_from: dueFrom || undefined,
    due_to: dueTo || undefined,
    overdue_only: overdueOnly,
  }, !invalidDateRange);
  const cases = overviewQuery.data?.items ?? [];
  const total = overviewQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(query || taskStatus || dueFrom || dueTo || overdueOnly);
  const isLoading = sessionStatus === "loading" || overviewQuery.isLoading;
  const errorMessage = overviewQuery.error instanceof Error
    ? overviewQuery.error.message
    : "We couldn’t load offboarding cases from this workspace.";

  function updateSearch(value: string) {
    setSearchInput(value);
    setPage(1);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setQuery(value.trim()), 250);
  }

  function clearFilters() {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = null;
    setSearchInput("");
    setQuery("");
    setTaskStatus("");
    setDueFrom("");
    setDueTo("");
    setOverdueOnly(false);
    setPage(1);
  }

  return (
    <div className="mx-auto flex w-full max-w-375 flex-col gap-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-sr-green">People operations</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">Offboarding</h1>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Track employee departures, checklist progress, and upcoming or overdue tasks in one place.
        </p>
      </header>

      <section
        aria-label="Offboarding filters"
        className="grid min-w-0 gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-5"
      >
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600 xl:col-span-2">
          Search cases
          <input
            type="search"
            value={searchInput}
            onChange={(event) => updateSearch(event.target.value)}
            placeholder="Employee, job title, department"
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600">
          Cases with a task status
          <select
            value={taskStatus}
            onChange={(event) => {
              setTaskStatus(event.target.value as EmployeeOffboardingTaskStatus | "");
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All task statuses</option>
            {taskStatuses.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600">
          Task due from
          <input
            type="date"
            value={dueFrom}
            max={dueTo || undefined}
            onChange={(event) => {
              setDueFrom(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600">
          Task due to
          <input
            type="date"
            value={dueTo}
            min={dueFrom || undefined}
            onChange={(event) => {
              setDueTo(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3 sm:col-span-2 xl:col-span-5">
          <label className="flex min-h-10 items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={overdueOnly}
              onChange={(event) => {
                setOverdueOnly(event.target.checked);
                setPage(1);
              }}
              className="h-4 w-4 rounded border-gray-300 accent-sr-green focus:ring-sr-green"
            />
            Show cases with overdue tasks only
          </label>
          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-sm font-medium text-sr-text-blue underline-offset-4 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
        <p className="text-xs text-gray-500 sm:col-span-2 xl:col-span-5">
          Task status and due-date filters must match the same checklist task.
        </p>
        {invalidDateRange && (
          <p role="alert" className="text-sm text-red-800 sm:col-span-2 xl:col-span-5">
            The start of the due-date range must be on or before its end.
          </p>
        )}
      </section>

      <section aria-label="Active offboarding cases" className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <p role="status" className="p-10 text-center text-sm text-gray-600">Loading offboarding cases…</p>
        ) : sessionStatus !== "authenticated" ? (
          <p className="p-10 text-center text-sm text-gray-600">Sign in with a workspace admin or People Operations account to view offboarding.</p>
        ) : invalidDateRange ? (
          <p className="p-10 text-center text-sm text-gray-600">Update the due-date range to view matching cases.</p>
        ) : overviewQuery.isError ? (
          <div className="p-10 text-center">
            <p role="alert" className="text-sm text-red-800">{errorMessage}</p>
            <button type="button" onClick={() => void overviewQuery.refetch()} className="mt-3 text-sm font-medium text-sr-text-blue underline">Try again</button>
          </div>
        ) : cases.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <h2 className="text-base font-semibold text-sr-text-blue">
              {hasFilters ? "No offboarding cases match these filters" : "No active offboarding cases"}
            </h2>
            <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600">
              {hasFilters
                ? "Try changing or clearing the search and filters."
                : "When People Operations starts offboarding from an employee record, the case and its checklist will appear here."}
            </p>
            {hasFilters && (
              <button type="button" onClick={clearFilters} className="mt-4 text-sm font-medium text-sr-text-blue underline">
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="px-4 py-3 text-sm text-gray-600 sm:px-5">
              {total} active {total === 1 ? "case" : "cases"}
              {hasFilters ? " match the selected filters" : " in this workspace"}
            </div>

            <div className="divide-y divide-gray-100 md:hidden">
              {cases.map((item) => (
                <article key={item.employee_id} className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <EmployeeLink item={item} />
                      <p className="mt-0.5 text-sm text-gray-700">{item.job_title}</p>
                      <p className="text-xs text-gray-500">{item.department || "No department"}{item.location ? ` · ${item.location}` : ""}</p>
                    </div>
                    {item.overdue_task_count > 0 && (
                      <span className="shrink-0 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-800">
                        {item.overdue_task_count} overdue
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-gray-500">Last working day</p>
                      <p className="mt-0.5 font-medium text-gray-800">{formatDate(item.last_working_day)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Next task due</p>
                      <p className="mt-0.5 font-medium text-gray-800">{formatDate(item.next_due_date)}</p>
                    </div>
                  </div>
                  <CaseProgress item={item} />
                  <Link href={`/dashboard/applications/${item.application_id}`} className="inline-flex min-h-10 items-center text-sm font-semibold text-sr-text-blue underline-offset-4 hover:underline">
                    Open employee record
                  </Link>
                </article>
              ))}
            </div>

            <div className="hidden max-w-full overflow-x-auto overscroll-x-contain md:block">
              <table className="w-full min-w-[980px] text-left text-sm">
                <thead className="border-y border-gray-200 bg-gray-50 text-xs font-medium uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-5 py-3">Employee</th>
                    <th scope="col" className="px-5 py-3">Last working day</th>
                    <th scope="col" className="px-5 py-3">Checklist progress</th>
                    <th scope="col" className="px-5 py-3">Overdue</th>
                    <th scope="col" className="px-5 py-3">Next task due</th>
                    <th scope="col" className="px-5 py-3"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {cases.map((item) => (
                    <tr key={item.employee_id} className="transition-colors hover:bg-gray-50">
                      <td className="px-5 py-4">
                        <EmployeeLink item={item} />
                        <p className="mt-0.5 text-xs text-gray-600">{item.job_title}</p>
                        <p className="text-xs text-gray-500">{item.department || "No department"}{item.location ? ` · ${item.location}` : ""}</p>
                      </td>
                      <td className="px-5 py-4 text-gray-700">{formatDate(item.last_working_day)}</td>
                      <td className="px-5 py-4"><CaseProgress item={item} /></td>
                      <td className="px-5 py-4">
                        {item.overdue_task_count > 0 ? (
                          <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-800">
                            {item.overdue_task_count} {item.overdue_task_count === 1 ? "task" : "tasks"}
                          </span>
                        ) : <span className="text-gray-500">None</span>}
                      </td>
                      <td className="px-5 py-4 text-gray-700">{formatDate(item.next_due_date)}</td>
                      <td className="px-5 py-4 text-right">
                        <Link href={`/dashboard/applications/${item.application_id}`} className="font-medium text-sr-text-blue hover:underline">
                          Open record
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <footer className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p aria-live="polite" className="text-sm text-gray-600">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} cases
              </p>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || overviewQuery.isFetching}
                  className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="min-w-20 text-center text-sm text-gray-600">Page {page} of {pageCount}</span>
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  disabled={page >= pageCount || overviewQuery.isFetching}
                  className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
