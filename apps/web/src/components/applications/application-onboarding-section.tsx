"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { ApiError } from "@/lib/api";
import {
  useApplicationOnboarding,
  useAssignOnboardingTask,
  useCompleteOnboarding,
  useStartApplicationOnboarding,
  useUpdateOnboardingTaskStatus,
} from "@/lib/api/hooks/onboarding";
import { useOnboardingTemplates } from "@/lib/api/hooks/onboarding";
import { useTeamMembers } from "@/lib/api/hooks/team";
import type {
  OnboardingTaskResponse,
  OnboardingTaskStatus,
} from "@/types/api/onboarding";

const taskLabels: Record<OnboardingTaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
  cancelled: "Cancelled",
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function dateLabel(value: string | null): string {
  if (!value) return "No due date";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

function TaskRow({
  applicationId,
  task,
  stepNumber,
  blockingTask,
}: {
  applicationId: string;
  task: OnboardingTaskResponse;
  stepNumber: number;
  blockingTask: OnboardingTaskResponse | null;
}) {
  const members = useTeamMembers();
  const assignTask = useAssignOnboardingTask();
  const updateStatus = useUpdateOnboardingTaskStatus();
  const [blockedReason, setBlockedReason] = useState(task.blocked_reason ?? "");
  const [resolutionNote, setResolutionNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const active = !blockingTask && task.status !== "completed" && task.status !== "cancelled";

  function changeStatus(target: OnboardingTaskStatus) {
    if (target === "blocked" && !blockedReason.trim()) {
      setError("Add a short reason before marking this task blocked.");
      return;
    }
    const resolvingEmployeeBlocker =
      task.responsible_party === "employee" &&
      task.status === "blocked" &&
      target === "in_progress";
    if (resolvingEmployeeBlocker && !resolutionNote.trim()) {
      setError("Add a response for the employee before reopening this task.");
      return;
    }
    setError(null);
    updateStatus.mutate({
      taskId: task.id,
      applicationId,
      request: {
        expected_version: task.version,
        target_status: target,
        blocked_reason: target === "blocked" ? blockedReason.trim() : null,
        resolution_note: resolvingEmployeeBlocker ? resolutionNote.trim() : null,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setBlockedReason("");
        setResolutionNote("");
      },
      onError: (cause) => setError(errorMessage(cause, "The task changed elsewhere or could not be updated. Refresh and try again.")),
    });
  }

  return (
    <li className={`rounded-lg border p-4 ${blockingTask ? "border-gray-200 bg-gray-50" : "border-gray-200 bg-white"}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${task.status === "completed" ? "bg-emerald-100 text-emerald-800" : blockingTask ? "bg-gray-200 text-gray-500" : "bg-blue-100 text-sr-text-blue"}`} aria-hidden="true">
            {task.status === "completed" ? "✓" : stepNumber}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-medium text-gray-900">{task.title}</h3>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${task.status === "completed" ? "bg-emerald-50 text-emerald-800" : blockingTask ? "bg-gray-200 text-gray-600" : task.status === "blocked" ? "bg-amber-100 text-amber-900" : "bg-blue-50 text-blue-800"}`}>
                {blockingTask ? "Locked" : taskLabels[task.status]}
              </span>
            </div>
            {task.description && <p className="mt-1 whitespace-pre-wrap text-sm text-gray-600">{task.description}</p>}
            <p className="mt-2 text-xs font-medium text-gray-600">
              {task.responsible_party === "employee" ? "Employee-owned step" : "Workspace-owned step"}
            </p>
            <p className="mt-2 text-xs text-gray-500">{task.due_at ? `Due ${dateLabel(task.due_at)}` : "No due date"}</p>
            {blockingTask && <p className="mt-2 text-sm text-gray-600">
              {blockingTask.status === "cancelled"
                ? `“${blockingTask.title}” was cancelled. Ask People Ops to review the plan before continuing.`
                : `Complete “${blockingTask.title}” first to unlock this task.`}
            </p>}
            {task.resolution_note && <p className="mt-3 whitespace-pre-wrap rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-blue-950"><span className="font-semibold">People Operations response: </span>{task.resolution_note}</p>}
          </div>
        </div>
        {active && (
          <label className="shrink-0">
            <span className="sr-only">Update status for {task.title}</span>
            <select value={task.status} disabled={updateStatus.isPending} onChange={(event) => changeStatus(event.target.value as OnboardingTaskStatus)} className="h-10 w-full cursor-pointer rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto">
              <option value={task.status}>{taskLabels[task.status]}</option>
              {task.status === "not_started" && <><option value="in_progress">In progress</option><option value="blocked">Blocked</option></>}
              {task.status === "in_progress" && <><option value="completed">Completed</option><option value="blocked">Blocked</option></>}
              {task.status === "blocked" && <option value="in_progress" disabled={task.responsible_party === "employee" && !resolutionNote.trim()}>{task.responsible_party === "employee" ? "Reopen after response" : "In progress"}</option>}
            </select>
          </label>
        )}
      </div>
      {active && (
        <div className="mt-4 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-2">
          {task.responsible_party === "workspace" && (
            <>
              <label>
                <span className="mb-1 block text-xs font-medium text-gray-600">Assigned to</span>
                <select value={task.assignee_user_id ?? ""} disabled={!active || members.isLoading || !members.data || assignTask.isPending} onChange={(event) => {
                  const assignee = event.target.value;
                  if (!assignee || assignee === task.assignee_user_id) return;
                  assignTask.mutate({
                    taskId: task.id,
                    applicationId,
                    request: { assignee_user_id: assignee, expected_task_version: task.version },
                    idempotencyKey: crypto.randomUUID(),
                  }, { onError: (cause) => setError(errorMessage(cause, "The task could not be assigned. Refresh and try again.")) });
                }} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                  <option value="">Unassigned</option>
                  {members.data?.items.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}
                </select>
              </label>
              {members.isError && <p className="text-sm text-red-800 sm:col-span-2">We couldn’t load workspace members to assign tasks.</p>}
            </>
          )}
          {task.status !== "blocked" && (
            <label>
              <span className="mb-1 block text-xs font-medium text-gray-600">Block reason (required to mark blocked)</span>
              <input value={blockedReason} onChange={(event) => setBlockedReason(event.target.value)} maxLength={2000} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
            </label>
          )}
          {task.status === "blocked" && task.responsible_party === "employee" && (
            <label className="sm:col-span-2">
              <span className="mb-1 block text-xs font-medium text-gray-700">Response for the employee (required to reopen)</span>
              <textarea value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} maxLength={2000} rows={3} className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="Explain what was done or what the employee should do next." />
              <span className="mt-1 block text-xs text-gray-500">Enter the guidance, then choose “Reopen after response” from the status menu.</span>
            </label>
          )}
        </div>
      )}
      {task.blocked_reason && <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900">Blocked: {task.blocked_reason}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
    </li>
  );
}

export function ApplicationOnboardingSection({
  applicationId,
  applicationStatus,
}: {
  applicationId: string;
  applicationStatus: string;
}) {
  const eligible = applicationStatus === "hired";
  const { data: session } = useSession();
  const canManageTemplates = session?.roles?.some((role) =>
    role === "tenant_admin" || role === "people_operations",
  ) ?? false;
  const onboarding = useApplicationOnboarding(applicationId, eligible);
  const templates = useOnboardingTemplates(eligible);
  const start = useStartApplicationOnboarding();
  const complete = useCompleteOnboarding();
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const instance = onboarding.data?.instance;
  const tasks = onboarding.data?.tasks ?? [];
  const allTasksComplete = tasks.length > 0 && tasks.every((task) => task.status === "completed");
  const nextTaskIndex = tasks.findIndex((task) => task.status !== "completed");
  const nextTask = nextTaskIndex >= 0 ? tasks[nextTaskIndex] : undefined;
  const progressPercent = tasks.length
    ? Math.round((tasks.filter((task) => task.status === "completed").length / tasks.length) * 100)
    : 0;

  if (!eligible) return null;

  return (
    <section aria-labelledby="application-onboarding-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-onboarding-heading" className="text-base font-semibold text-sr-text-blue">New hire onboarding</h2>
        <p className="mt-1 text-sm text-gray-600">Follow the steps in order. Each task unlocks after the previous task is completed.</p>
      </div>

      {onboarding.isLoading ? (
        <p className="mt-5 text-sm text-gray-600" role="status">Loading onboarding…</p>
      ) : onboarding.isError ? (
        <p className="mt-5 text-sm text-red-800" role="alert">We couldn’t load onboarding for this application.</p>
      ) : !instance ? (
        <div className="mt-5 space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4 sm:p-5">
          <ol className="space-y-3">
            <li className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-sm font-semibold text-emerald-800" aria-hidden="true">✓</span>
              <div><p className="font-medium text-gray-900">Application is hired</p><p className="text-sm text-gray-600">This candidate is ready for onboarding.</p></div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-sr-text-blue" aria-hidden="true">2</span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-gray-900">Choose an onboarding plan</p>
                <p className="mt-0.5 text-sm text-gray-600">The plan’s tasks will be completed in the order they are listed.</p>
              </div>
            </li>
          </ol>
          {templates.isLoading ? <p className="text-sm text-gray-600">Loading templates…</p> : templates.isError ? (
            <p role="alert" className="text-sm text-red-800">We couldn’t load onboarding templates.</p>
          ) : !templates.data?.items.length ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="font-medium text-amber-950">An onboarding plan is needed before you can continue.</p>
              <p className="mt-1 text-sm text-amber-900">A workspace admin or People Ops member must create a template in Settings → Onboarding.</p>
              {canManageTemplates && <Link href="/dashboard/settings" className="mt-3 inline-flex font-medium text-sr-text-blue underline">Open Settings, then choose Onboarding</Link>}
            </div>
          ) : (
            <div className="space-y-2 border-t border-gray-200 pt-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="flex-1">
                <span className="mb-1 block text-sm font-medium text-gray-700">Select a plan</span>
                <select value={templateId} onChange={(event) => setTemplateId(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                  <option value="">Choose an onboarding plan</option>
                  {templates.data.items.map((template) => <option key={template.id} value={template.id}>{template.name} · {template.tasks.length} tasks</option>)}
                </select>
              </label>
              <button type="button" disabled={!templateId || start.isPending} onClick={() => {
                setError(null);
                start.mutate({ applicationId, request: { onboarding_template_id: templateId }, idempotencyKey: crypto.randomUUID() }, { onError: (cause) => setError(errorMessage(cause, "Onboarding could not be started. Refresh and try again.")) });
              }} className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">{start.isPending ? "Starting…" : "Start onboarding"}</button>
              </div>
              <p className="text-xs text-gray-500">Starting the plan creates an employee record if one does not exist. You can add or update employment details in the Employee record section above.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 sm:p-5">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{instance.status === "active" && nextTask ? nextTask.status === "cancelled" ? "Plan needs review" : `Next up · Step ${nextTaskIndex + 1} of ${tasks.length}` : "Onboarding status"}</p>
                  <p className="mt-1 text-lg font-semibold text-gray-900">{instance.status === "active" ? nextTask?.status === "cancelled" ? "A task was cancelled" : nextTask?.title ?? "All tasks are complete" : `Onboarding ${instance.status}`}</p>
                  {instance.status === "active" && nextTask?.status === "cancelled" && <p className="mt-1 text-sm text-amber-900">Ask People Ops to review the plan before continuing.</p>}
                  <p className="mt-1 text-sm text-gray-600">Started {dateLabel(instance.started_at)}</p>
                </div>
                {instance.status === "active" && (
                  <div className="flex flex-col items-start gap-1 sm:items-end">
                    <button
                      type="button"
                      disabled={!allTasksComplete || complete.isPending}
                      onClick={() => complete.mutate({
                        instanceId: instance.id,
                        applicationId,
                        request: { expected_instance_version: instance.version },
                        idempotencyKey: crypto.randomUUID(),
                      }, {
                        onError: (cause) => setError(errorMessage(cause, "Complete all onboarding tasks before finishing this plan.")),
                      })}
                      className="h-10 cursor-pointer rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {complete.isPending ? "Completing…" : "Complete onboarding"}
                    </button>
                    {!allTasksComplete && <p className="text-xs text-gray-500">Complete every task first.</p>}
                  </div>
                )}
              </div>
              <div className="mt-4">
                <div className="flex justify-between gap-3 text-xs text-gray-600"><span>{tasks.filter((task) => task.status === "completed").length} of {tasks.length} tasks completed</span><span>{progressPercent}%</span></div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-200" role="progressbar" aria-label="Onboarding progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}><div className="h-full rounded-full bg-sr-green transition-[width]" style={{ width: `${progressPercent}%` }} /></div>
              </div>
            </div>
          </div>
          {tasks.length ? <ol className="space-y-3" aria-label="Onboarding tasks in order">{tasks.map((task, index) => {
            const blockingTask = tasks.slice(0, index).find((previous) => previous.status !== "completed") ?? null;
            return <TaskRow key={task.id} applicationId={applicationId} task={task} stepNumber={index + 1} blockingTask={blockingTask} />;
          })}</ol> : <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">This plan has no tasks. Ask a workspace admin or People Ops member to review the onboarding template.</p>}
        </div>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
      {instance?.status === "active" && <p className="mt-4 text-xs text-gray-500">Tasks must be completed in order. You can assign or update the current task; later tasks stay locked until it is complete.</p>}
    </section>
  );
}
