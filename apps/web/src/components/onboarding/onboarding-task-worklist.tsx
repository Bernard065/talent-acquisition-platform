"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import { ApiError } from "@/lib/api";
import {
  useAssignOnboardingTask,
  useOnboardingTaskWorklist,
  useUpdateOnboardingTaskDueDate,
  useUpdateOnboardingTaskStatus,
} from "@/lib/api/hooks/onboarding";
import { useTeamMembers } from "@/lib/api/hooks/team";
import { OnboardingTaskDocumentList } from "@/components/onboarding/onboarding-task-document-list";
import type {
  OnboardingTaskStatus,
  OnboardingTaskWorklistItemResponse,
  OnboardingTaskWorklistView,
} from "@/types/api/onboarding";
import type { TeamMember } from "@/types/api/team";

const PAGE_SIZE = 25;

const viewOptions: Array<{
  value: OnboardingTaskWorklistView;
  label: string;
}> = [
  { value: "open", label: "Open" },
  { value: "due_soon", label: "Due soon" },
  { value: "overdue", label: "Overdue" },
  { value: "completed", label: "Completed" },
];

const taskStatusLabels: Record<OnboardingTaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
  cancelled: "Cancelled",
};

function formatDate(value: string | null): string {
  if (!value) return "No due date";
  const date = value.length === 10 ? new Date(`${value}T00:00:00Z`) : new Date(value);
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(date);
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function statusClasses(status: OnboardingTaskStatus): string {
  if (status === "completed") return "bg-emerald-50 text-emerald-800";
  if (status === "blocked") return "bg-amber-50 text-amber-900";
  if (status === "cancelled") return "bg-gray-100 text-gray-600";
  return "bg-blue-50 text-blue-800";
}

function TaskWorklistRow({
  item,
  canEditDueDates,
  members,
  membersLoading,
  membersError,
}: {
  item: OnboardingTaskWorklistItemResponse;
  canEditDueDates: boolean;
  members: TeamMember[];
  membersLoading: boolean;
  membersError: boolean;
}) {
  const assignTask = useAssignOnboardingTask();
  const updateStatus = useUpdateOnboardingTaskStatus();
  const updateDueDate = useUpdateOnboardingTaskDueDate();
  const [dueDateDraft, setDueDateDraft] = useState(item.task.due_at?.slice(0, 10) ?? "");
  const [error, setError] = useState<string | null>(null);
  const task = item.task;
  const isActive = item.instance_status === "active";
  const isIncomplete = task.status !== "completed" && task.status !== "cancelled";
  const hasAvailableDocument = task.documents.some(
    (document) => document.status === "available",
  );
  const hasAcceptedDocument = task.documents.some(
    (document) => document.status === "available" && document.review_status === "accepted",
  );
  const canCompleteDocumentRequirement = task.requires_document_review
    ? hasAcceptedDocument
    : hasAvailableDocument;
  const currentDueDate = task.due_at?.slice(0, 10) ?? "";
  const isPending = assignTask.isPending || updateStatus.isPending || updateDueDate.isPending;
  const memberOptions = task.assignee_user_id && item.assignee_display_name &&
    !members.some((member) => member.id === task.assignee_user_id)
    ? [...members, { id: task.assignee_user_id, display_name: item.assignee_display_name, email: "" }]
    : members;

  const statusAction = task.status === "not_started"
    ? { target: "in_progress" as const, label: "Start task" }
    : task.status === "in_progress"
      ? task.requires_document_upload && !canCompleteDocumentRequirement
        ? null
        : { target: "completed" as const, label: "Mark complete" }
      : task.status === "blocked" && task.responsible_party === "workspace"
        ? { target: "in_progress" as const, label: "Resume task" }
        : null;

  function changeStatus(targetStatus: OnboardingTaskStatus) {
    setError(null);
    updateStatus.mutate({
      taskId: task.id,
      applicationId: item.application_id,
      request: {
        expected_version: task.version,
        target_status: targetStatus,
        blocked_reason: null,
        resolution_note: null,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onError: (cause) => setError(
        getErrorMessage(cause, "The task could not be updated. Refresh and try again."),
      ),
    });
  }

  function changeAssignee(value: string) {
    const assigneeUserId = value || null;
    if (assigneeUserId === task.assignee_user_id) return;
    setError(null);
    assignTask.mutate({
      taskId: task.id,
      applicationId: item.application_id,
      request: {
        assignee_user_id: assigneeUserId,
        expected_task_version: task.version,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onError: (cause) => setError(
        getErrorMessage(cause, "The task could not be assigned. Refresh and try again."),
      ),
    });
  }

  function saveDueDate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    updateDueDate.mutate({
      taskId: task.id,
      applicationId: item.application_id,
      request: {
        due_date: dueDateDraft || null,
        expected_task_version: task.version,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onError: (cause) => setError(
        getErrorMessage(cause, "The due date could not be updated. Refresh and try again."),
      ),
    });
  }

  return (
    <article className="grid gap-3 border-b border-gray-100 px-4 py-4 last:border-b-0 md:grid-cols-[1.5fr_1.5fr_1.15fr_1.5fr_1.7fr] md:items-start md:px-5">
      <div className="min-w-0">
        <span className="mb-1 block text-xs font-medium text-gray-500 md:hidden">Task</span>
        <p className="font-medium text-gray-900">{task.title}</p>
        <p className="mt-1 text-xs text-gray-500">
          Step {item.step_number} · {task.responsible_party === "employee" ? "Employee step" : "Workspace step"}
        </p>
        {task.description && <p className="mt-1 line-clamp-2 text-xs text-gray-600">{task.description}</p>}
      </div>

      <div className="min-w-0">
        <span className="mb-1 block text-xs font-medium text-gray-500 md:hidden">New hire</span>
        <p className="truncate text-sm font-medium text-gray-900">{item.employee_name}</p>
        <p className="truncate text-xs text-gray-600">{item.job_title}</p>
      </div>

      <div className="min-w-0">
        <span className="mb-1 block text-xs font-medium text-gray-500 md:hidden">Assigned to</span>
        {task.responsible_party === "employee" ? (
          <span className="text-sm text-gray-700">New hire</span>
        ) : isActive && isIncomplete ? (
          <select
            aria-label={`Assign ${task.title}`}
            value={task.assignee_user_id ?? ""}
            disabled={!item.can_update || isPending || membersLoading || membersError}
            onChange={(event) => changeAssignee(event.target.value)}
            className="h-9 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-700 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500"
          >
            <option value="">Unassigned</option>
            {memberOptions.map((member) => (
              <option key={member.id} value={member.id}>{member.display_name}</option>
            ))}
          </select>
        ) : (
          <span className="text-sm text-gray-700">{item.assignee_display_name ?? "Unassigned"}</span>
        )}
        {task.responsible_party === "workspace" && membersError && (
          <p className="mt-1 text-xs text-red-800">Members unavailable</p>
        )}
      </div>

      <div className="min-w-0">
        <span className="mb-1 block text-xs font-medium text-gray-500 md:hidden">Due date</span>
        {canEditDueDates && isActive && isIncomplete ? (
          <form className="flex flex-wrap items-center gap-2" onSubmit={saveDueDate}>
            <label className="sr-only" htmlFor={`due-date-${task.id}`}>Due date for {task.title}</label>
            <input
              id={`due-date-${task.id}`}
              type="date"
              value={dueDateDraft}
              onChange={(event) => setDueDateDraft(event.target.value)}
              disabled={isPending}
              className="h-9 min-w-0 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={isPending || dueDateDraft === currentDueDate}
              className="h-9 cursor-pointer rounded-lg border border-gray-300 px-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Save
            </button>
          </form>
        ) : (
          <span className="text-sm text-gray-700">
            {formatDate(task.due_at)}
          </span>
        )}
      </div>

      {task.requires_document_upload && (
        <div className="md:col-span-full">
          <OnboardingTaskDocumentList documents={task.documents} />
          {task.requires_document_upload && !canCompleteDocumentRequirement && task.status === "in_progress" && (
            <p className="mt-2 text-xs text-gray-600">
              {task.requires_document_review
                ? "The task can be completed after People Operations accepts a clean file."
                : "The task can be completed after the employee’s file passes its security scan."}
            </p>
          )}
        </div>
      )}

      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="mb-1 w-full text-xs font-medium text-gray-500 md:hidden">Status and actions</span>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClasses(task.status)}`}>
          {taskStatusLabels[task.status]}
        </span>
        {statusAction && (
          <button
            type="button"
            disabled={!item.can_update || isPending}
            onClick={() => changeStatus(statusAction.target)}
            className="min-h-9 cursor-pointer rounded-lg bg-sr-text-blue px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {updateStatus.isPending ? "Saving…" : statusAction.label}
          </button>
        )}
        {!item.can_update && isActive && isIncomplete && (
          <span className="text-xs text-gray-500">Waiting for earlier step</span>
        )}
        <Link
          href={`/dashboard/applications/${item.application_id}#application-onboarding-heading`}
          className="min-h-9 rounded-lg px-2 py-2 text-xs font-semibold text-sr-text-blue hover:bg-blue-50 hover:underline"
        >
          Open plan
        </Link>
        {error && <p className="w-full text-xs text-red-800" role="alert">{error}</p>}
      </div>
    </article>
  );
}

export function OnboardingTaskWorklist() {
  const { data: session } = useSession();
  const [view, setView] = useState<OnboardingTaskWorklistView>("open");
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({
    page,
    limit: PAGE_SIZE,
    view,
    query: query || undefined,
    assignee_user_id: assigneeFilter && assigneeFilter !== "unassigned"
      ? assigneeFilter
      : undefined,
    unassigned_only: assigneeFilter === "unassigned" || undefined,
  }), [assigneeFilter, page, query, view]);
  const worklist = useOnboardingTaskWorklist(params);
  const members = useTeamMembers();
  const items = worklist.data?.items ?? [];
  const assignees = worklist.data?.assignees ?? [];
  const canEditDueDates = session?.roles?.some((role) =>
    role === "tenant_admin" || role === "people_operations",
  ) ?? false;
  const total = worklist.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isLoading = worklist.isLoading;

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  function changeView(nextView: OnboardingTaskWorklistView) {
    setView(nextView);
    setPage(1);
  }

  function changeAssignee(nextAssignee: string) {
    setAssigneeFilter(nextAssignee);
    setPage(1);
  }

  return (
    <section aria-labelledby="onboarding-task-worklist-heading" className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="border-b border-gray-200 px-4 py-5 sm:px-6">
        <h2 id="onboarding-task-worklist-heading" className="text-lg font-semibold text-sr-text-blue">Onboarding task worklist</h2>
        <p className="mt-1 text-sm text-gray-600">
          Find and update onboarding steps across new hires. Tasks unlock in plan order.
        </p>
        <div className="mt-4 flex flex-wrap gap-2" aria-label="Filter onboarding tasks by due status">
          {viewOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={view === option.value}
              onClick={() => changeView(option.value)}
              className={`min-h-9 cursor-pointer rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${view === option.value ? "border-sr-text-blue bg-sr-text-blue text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"}`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,0.55fr)]">
          <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
            Search tasks, new hires, or jobs
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Task, name, or job title"
              className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
            Assigned to
            <select
              value={assigneeFilter}
              onChange={(event) => changeAssignee(event.target.value)}
              className="h-10 cursor-pointer rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              <option value="">Everyone</option>
              <option value="unassigned">Unassigned</option>
              {assignees.map((assignee) => (
                <option key={assignee.id} value={assignee.id}>{assignee.display_name}</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {isLoading && !worklist.data ? (
        <p className="px-5 py-10 text-center text-sm text-gray-600" role="status">Loading onboarding tasks…</p>
      ) : worklist.isError && !worklist.data ? (
        <div className="px-5 py-10 text-center">
          <p className="text-sm text-red-800" role="alert">We couldn’t load onboarding tasks from your workspace.</p>
          <button type="button" onClick={() => void worklist.refetch()} className="mt-3 cursor-pointer text-sm font-medium text-sr-text-blue underline">Try again</button>
        </div>
      ) : items.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <h3 className="font-semibold text-sr-text-blue">
            {view === "completed" ? "No completed tasks found" : view === "overdue" ? "No overdue tasks" : view === "due_soon" ? "No tasks due soon" : "No open onboarding tasks"}
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            {query || assigneeFilter
              ? "Try changing the search or assignee filter."
              : view === "open"
                ? "Start an onboarding plan from a hired application to create tasks."
                : "Tasks that match this view will appear here."}
          </p>
          {(query || assigneeFilter) && (
            <button
              type="button"
              onClick={() => {
                setSearchInput("");
                setQuery("");
                setAssigneeFilter("");
                setPage(1);
              }}
              className="mt-3 cursor-pointer text-sm font-medium text-sr-text-blue underline"
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <>
          {worklist.isError && (
            <p className="mx-4 mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
              Couldn’t refresh tasks. Showing the last loaded results.
            </p>
          )}
          <div className="hidden grid-cols-[1.5fr_1.5fr_1.15fr_1.5fr_1.7fr] gap-3 border-b border-gray-100 bg-gray-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid">
            <span>Task</span><span>New hire and job</span><span>Assignee</span><span>Due date</span><span>Status and actions</span>
          </div>
          <div aria-live="polite">
            {items.map((item) => (
              <TaskWorklistRow
                key={`${item.task.id}-${item.task.version}`}
                item={item}
                canEditDueDates={canEditDueDates}
                members={members.data?.items ?? []}
                membersLoading={members.isLoading}
                membersError={members.isError}
              />
            ))}
          </div>
          <footer className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <p aria-live="polite" className="text-sm text-gray-600">
              Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} tasks
            </p>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <button type="button" disabled={page <= 1 || isLoading} onClick={() => setPage((current) => current - 1)} className="h-9 cursor-pointer rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50">Previous</button>
              <span className="px-1 text-sm text-gray-600">Page {page} of {pageCount}</span>
              <button type="button" disabled={page >= pageCount || isLoading} onClick={() => setPage((current) => current + 1)} className="h-9 cursor-pointer rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50">Next</button>
            </div>
          </footer>
        </>
      )}
    </section>
  );
}
