"use client";

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { ApiError } from "@/lib/api/errors";
import { useMyEmployeeOffboardingTasks, useUpdateEmployeeOffboardingTask } from "@/lib/api/hooks/employee-records";
import type {
  EmployeeOffboardingTaskStatus,
  MyEmployeeOffboardingTaskResponse,
} from "@/types/api/employee-records";

const PAGE_SIZE = 25;

const taskStatuses: { value: EmployeeOffboardingTaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" },
  { value: "completed", label: "Completed" },
];

/** Format a date-only API value without applying the viewer's local timezone. */
function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

/** Return whether an incomplete task's due date has passed in UTC. */
function isOverdue(value: string, status: EmployeeOffboardingTaskStatus): boolean {
  return status !== "completed" && value.slice(0, 10) < new Date().toISOString().slice(0, 10);
}

/** Choose the badge colors for a task's current status. */
function taskStatusStyle(status: EmployeeOffboardingTaskStatus): string {
  if (status === "completed") return "bg-emerald-50 text-emerald-800";
  if (status === "blocked") return "bg-red-50 text-red-800";
  if (status === "in_progress") return "bg-blue-50 text-blue-800";
  return "bg-gray-100 text-gray-700";
}

/** Give task owners an actionable message when an update fails. */
function getSaveError(error: unknown): string {
  if (error instanceof ApiError && error.isConflict) {
    return "This task changed elsewhere. Reload the task list and try again.";
  }
  return error instanceof Error ? error.message : "We couldn’t save this task. Try again.";
}

/** Render one assigned task with owner-editable progress and notes. */
function MyTaskCard({ task }: { task: MyEmployeeOffboardingTaskResponse }) {
  const updateTask = useUpdateEmployeeOffboardingTask();
  const [status, setStatus] = useState(task.status);
  const [notes, setNotes] = useState(task.completion_notes ?? "");
  const overdue = isOverdue(task.due_date, task.status);
  const changed = status !== task.status || notes !== (task.completion_notes ?? "");

  /** Persist this task's status and completion notes. */
  async function save() {
    try {
      await updateTask.mutateAsync({
        taskId: task.id,
        employeeId: task.employee_id,
        request: {
          expected_version: task.version,
          status,
          completion_notes: notes.trim() || null,
        },
        idempotencyKey: crypto.randomUUID(),
      });
    } catch {
      // The mutation error is rendered below with the API's message.
    }
  }

  return (
    <article className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-sr-text-blue">{task.title}</h2>
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${taskStatusStyle(task.status)}`}>
              {taskStatuses.find((option) => option.value === task.status)?.label ?? task.status}
            </span>
            {overdue && (
              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900">
                Overdue
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-gray-700">{task.employee_name} · {task.job_title}</p>
          {task.description && <p className="mt-2 whitespace-pre-wrap text-sm text-gray-600">{task.description}</p>}
          <p className={`mt-3 text-sm ${overdue ? "font-medium text-red-800" : "text-gray-600"}`}>
            Due {formatDate(task.due_date)}
          </p>
          {task.completed_at && (
            <p className="mt-1 text-xs text-gray-500">Completed {formatDate(task.completed_at)}</p>
          )}
        </div>

        <label className="flex w-full flex-col gap-1.5 text-xs font-medium text-gray-600 sm:w-48">
          Update status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as EmployeeOffboardingTaskStatus)}
            disabled={updateTask.isPending}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            {taskStatuses.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="mt-4 flex flex-col gap-1.5 text-xs font-medium text-gray-600">
        Completion notes
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          disabled={updateTask.isPending}
          maxLength={4000}
          rows={2}
          placeholder="Add a brief update or completion note"
          className="min-h-20 resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
        />
      </label>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="text-sm text-red-800">
          {updateTask.isError ? getSaveError(updateTask.error) : ""}
        </p>
        <button
          type="button"
          onClick={() => void save()}
          disabled={!changed || updateTask.isPending}
          className="inline-flex h-10 w-full cursor-pointer items-center justify-center rounded-lg bg-sr-green px-4 text-sm font-semibold text-white hover:bg-sr-green/90 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {updateTask.isPending ? "Saving…" : "Save update"}
        </button>
      </div>
    </article>
  );
}

/** Show the authenticated member's paginated offboarding task inbox. */
export default function MyOffboardingPage() {
  const { status: sessionStatus } = useSession();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [taskStatus, setTaskStatus] = useState<EmployeeOffboardingTaskStatus | "">("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [page, setPage] = useState(1);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
  }, []);

  const tasksQuery = useMyEmployeeOffboardingTasks({
    page,
    limit: PAGE_SIZE,
    query: query || undefined,
    task_status: taskStatus || undefined,
    overdue_only: overdueOnly || undefined,
  });
  const tasks = tasksQuery.data?.items ?? [];
  const total = tasksQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(searchInput || query || taskStatus || overdueOnly);
  const isLoading = sessionStatus === "loading" || tasksQuery.isLoading;
  const errorMessage = tasksQuery.error instanceof Error
    ? tasksQuery.error.message
    : "We couldn’t load your offboarding tasks.";

  /** Debounce the task search and return to the first result page. */
  function updateSearch(value: string) {
    setSearchInput(value);
    setPage(1);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setQuery(value.trim()), 250);
  }

  /** Reset search and filters to the full task list. */
  function clearFilters() {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = null;
    setSearchInput("");
    setQuery("");
    setTaskStatus("");
    setOverdueOnly(false);
    setPage(1);
  }

  return (
    <div className="mx-auto flex w-full max-w-375 flex-col gap-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-sr-green">Your workspace</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">My offboarding tasks</h1>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Review the tasks assigned to you, update their progress, and leave notes for your team.
        </p>
      </header>

      <section
        aria-label="My offboarding task filters"
        className="grid min-w-0 gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-[minmax(16rem,2fr)_minmax(12rem,1fr)_auto_auto] xl:items-end"
      >
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600">
          Search tasks
          <input
            type="search"
            value={searchInput}
            onChange={(event) => updateSearch(event.target.value)}
            placeholder="Task, employee, or job title"
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-xs font-medium text-gray-600">
          Status
          <select
            value={taskStatus}
            onChange={(event) => {
              setTaskStatus(event.target.value as EmployeeOffboardingTaskStatus | "");
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All statuses</option>
            {taskStatuses.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
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
          Overdue only
        </label>
        {hasFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="min-h-10 text-left text-sm font-medium text-sr-text-blue underline-offset-4 hover:underline"
          >
            Clear filters
          </button>
        )}
      </section>

      <section aria-label="Tasks assigned to me" className="min-w-0">
        {isLoading ? (
          <div className="rounded-xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-600" role="status">
            Loading your offboarding tasks…
          </div>
        ) : sessionStatus !== "authenticated" ? (
          <div className="rounded-xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-600">
            Sign in to view tasks assigned to you.
          </div>
        ) : tasksQuery.isError ? (
          <div className="rounded-xl border border-red-200 bg-white p-10 text-center">
            <p role="alert" className="text-sm text-red-800">{errorMessage}</p>
            <button type="button" onClick={() => void tasksQuery.refetch()} className="mt-3 text-sm font-medium text-sr-text-blue underline">
              Try again
            </button>
          </div>
        ) : tasks.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white px-6 py-14 text-center">
            <h2 className="text-base font-semibold text-sr-text-blue">
              {hasFilters ? "No assigned tasks match these filters" : "No offboarding tasks assigned to you"}
            </h2>
            <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600">
              {hasFilters
                ? "Change or clear the filters to see other tasks assigned to you."
                : "When a workspace admin or People Operations assigns you an offboarding task, it will appear here."}
            </p>
            {hasFilters && (
              <button type="button" onClick={clearFilters} className="mt-4 text-sm font-medium text-sr-text-blue underline">
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <>
            <p aria-live="polite" className="mb-3 text-sm text-gray-600">
              {total} {total === 1 ? "task" : "tasks"} assigned to you
            </p>
            <div className="flex flex-col gap-3">
              {tasks.map((task) => <MyTaskCard key={`${task.id}:${task.version}`} task={task} />)}
            </div>
            <footer className="mt-4 flex flex-col gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-gray-600">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} tasks
              </p>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || tasksQuery.isFetching}
                  className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="min-w-20 text-center text-sm text-gray-600">Page {page} of {pageCount}</span>
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  disabled={page >= pageCount || tasksQuery.isFetching}
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
