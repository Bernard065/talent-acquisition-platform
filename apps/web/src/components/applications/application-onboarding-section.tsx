"use client";

import { useState } from "react";
import {
  useApplicationOnboarding,
  useAssignOnboardingTask,
  useCompleteOnboarding,
  useStartApplicationOnboarding,
  useUpdateOnboardingTaskStatus,
} from "@/lib/api/hooks/onboarding";
import { useOnboardingTemplates } from "@/lib/api/hooks/onboarding";
import { useTeamMembers } from "@/lib/api/hooks/team";
import type { OnboardingTaskResponse, OnboardingTaskStatus } from "@/types/api/onboarding";

const taskLabels: Record<OnboardingTaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
  cancelled: "Cancelled",
};

function dateLabel(value: string | null): string {
  if (!value) return "No due date";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

function TaskRow({ applicationId, task }: { applicationId: string; task: OnboardingTaskResponse }) {
  const members = useTeamMembers();
  const assignTask = useAssignOnboardingTask();
  const updateStatus = useUpdateOnboardingTaskStatus();
  const [blockedReason, setBlockedReason] = useState(task.blocked_reason ?? "");
  const [error, setError] = useState<string | null>(null);
  const active = task.status !== "completed" && task.status !== "cancelled";

  function changeStatus(target: OnboardingTaskStatus) {
    if (target === "blocked" && !blockedReason.trim()) {
      setError("Add a short reason before marking this task blocked.");
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
      },
      idempotencyKey: crypto.randomUUID(),
    }, { onError: () => setError("The task changed elsewhere or could not be updated. Refresh and try again.") });
  }

  return (
    <li className="rounded-lg border border-gray-200 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="font-medium text-gray-900">{task.title}</h3>
          {task.description && <p className="mt-1 whitespace-pre-wrap text-sm text-gray-600">{task.description}</p>}
          <p className="mt-2 text-xs text-gray-500">Due {dateLabel(task.due_at)}</p>
        </div>
        <label className="shrink-0">
          <span className="sr-only">Status for {task.title}</span>
          <select value={task.status} disabled={!active || updateStatus.isPending} onChange={(event) => changeStatus(event.target.value as OnboardingTaskStatus)} className="h-10 w-full cursor-pointer rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto">
            <option value={task.status}>{taskLabels[task.status]}</option>
            {task.status === "not_started" && <><option value="in_progress">In progress</option><option value="blocked">Blocked</option></>}
            {task.status === "in_progress" && <><option value="completed">Completed</option><option value="blocked">Blocked</option></>}
            {task.status === "blocked" && <option value="in_progress">In progress</option>}
          </select>
        </label>
      </div>
      {active && (
        <div className="mt-4 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-2">
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
              }, { onError: () => setError("The task could not be assigned. Refresh and try again.") });
            }} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
              <option value="">Unassigned</option>
              {members.data?.items.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}
            </select>
          </label>
          {members.isError && <p className="text-sm text-red-800 sm:col-span-2">We couldn’t load workspace members to assign tasks.</p>}
          <label>
            <span className="mb-1 block text-xs font-medium text-gray-600">Block reason (required to mark blocked)</span>
            <input value={blockedReason} onChange={(event) => setBlockedReason(event.target.value)} maxLength={2000} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
          </label>
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
  const onboarding = useApplicationOnboarding(applicationId, eligible);
  const templates = useOnboardingTemplates(eligible);
  const start = useStartApplicationOnboarding();
  const complete = useCompleteOnboarding();
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const instance = onboarding.data?.instance;
  const tasks = onboarding.data?.tasks ?? [];
  const allTasksComplete = tasks.length > 0 && tasks.every((task) => task.status === "completed");

  if (!eligible) return null;

  return (
    <section aria-labelledby="application-onboarding-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-onboarding-heading" className="text-base font-semibold text-sr-text-blue">New hire onboarding</h2>
        <p className="mt-1 text-sm text-gray-600">Start a task plan for this hired candidate and track its progress.</p>
      </div>

      {onboarding.isLoading ? (
        <p className="mt-5 text-sm text-gray-600" role="status">Loading onboarding…</p>
      ) : onboarding.isError ? (
        <p className="mt-5 text-sm text-red-800" role="alert">We couldn’t load onboarding for this application.</p>
      ) : !instance ? (
        <div className="mt-5 rounded-lg bg-gray-50 p-4">
          {templates.isLoading ? <p className="text-sm text-gray-600">Loading templates…</p> : templates.isError ? (
            <p role="alert" className="text-sm text-red-800">We couldn’t load onboarding templates.</p>
          ) : !templates.data?.items.length ? (
            <p className="text-sm text-gray-700">There are no onboarding templates yet. A workspace admin or People Ops member can create one in <strong>Settings → Onboarding</strong>.</p>
          ) : (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="flex-1">
                <span className="mb-1 block text-sm font-medium text-gray-700">Onboarding plan</span>
                <select value={templateId} onChange={(event) => setTemplateId(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                  <option value="">Choose a template</option>
                  {templates.data.items.map((template) => <option key={template.id} value={template.id}>{template.name} · {template.tasks.length} tasks</option>)}
                </select>
              </label>
              <button type="button" disabled={!templateId || start.isPending} onClick={() => {
                setError(null);
                start.mutate({ applicationId, request: { onboarding_template_id: templateId }, idempotencyKey: crypto.randomUUID() }, { onError: () => setError("Onboarding could not be started. Refresh and try again.") });
              }} className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">{start.isPending ? "Starting…" : "Start onboarding"}</button>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-gray-50 p-4">
            <div>
              <p className="text-sm font-semibold text-gray-900">{instance.status === "active" ? "Onboarding in progress" : `Onboarding ${instance.status}`}</p>
              <p className="mt-1 text-xs text-gray-600">Started {dateLabel(instance.started_at)}</p>
            </div>
            {instance.status === "active" && <button type="button" disabled={!allTasksComplete || complete.isPending} onClick={() => complete.mutate({ instanceId: instance.id, applicationId, request: { expected_instance_version: instance.version }, idempotencyKey: crypto.randomUUID() }, { onError: () => setError("Complete all onboarding tasks before finishing this plan.") })} className="h-10 rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50">{complete.isPending ? "Completing…" : "Complete onboarding"}</button>}
          </div>
          {tasks.length ? <ul className="space-y-3">{tasks.map((task) => <TaskRow key={task.id} applicationId={applicationId} task={task} />)}</ul> : <p className="text-sm text-red-800">This onboarding plan has no tasks. Contact a workspace administrator.</p>}
        </div>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
      {instance?.status === "active" && <p className="mt-4 text-xs text-gray-500">If an active HRIS connection is configured, the handoff is queued when onboarding starts.</p>}
    </section>
  );
}
