"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { OnboardingTaskActivity } from "@/components/onboarding/onboarding-task-activity";
import {
  useEmployeePortalOnboarding,
  useUploadEmployeeOnboardingTaskDocument,
  useUpdateEmployeePortalTaskStatus,
} from "@/lib/api/hooks/onboarding";
import type {
  EmployeePortalTaskResponse,
  OnboardingInstanceStatus,
  OnboardingTaskStatus,
} from "@/types/api/onboarding";

const planStatusLabels: Record<OnboardingInstanceStatus, string> = {
  active: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

const taskStatusLabels: Record<OnboardingTaskStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Needs help",
  cancelled: "Cancelled",
};

function formatDate(value: string | null): string {
  if (!value) return "Not set";
  const date = value.length === 10 ? new Date(`${value}T00:00:00Z`) : new Date(value);
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(date);
}

function taskStatusStyle(status: OnboardingTaskStatus): string {
  if (status === "completed") return "bg-emerald-50 text-emerald-800";
  if (status === "blocked") return "bg-red-50 text-red-800";
  if (status === "in_progress") return "bg-blue-50 text-blue-800";
  if (status === "cancelled") return "bg-gray-100 text-gray-600";
  return "bg-amber-50 text-amber-900";
}

function TaskItem({
  task,
  position,
  blockedByEarlierStep,
  planActive,
  updatePending,
  onUpdate,
}: {
  task: EmployeePortalTaskResponse;
  position: number;
  blockedByEarlierStep: boolean;
  planActive: boolean;
  updatePending: boolean;
  onUpdate: (
    task: EmployeePortalTaskResponse,
    targetStatus: "in_progress" | "completed" | "blocked",
    blockedReason?: string,
  ) => void;
}) {
  const [showHelpForm, setShowHelpForm] = useState(false);
  const [helpReason, setHelpReason] = useState("");
  const [helpError, setHelpError] = useState<string | null>(null);
  const uploadDocument = useUploadEmployeeOnboardingTaskDocument();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const hasAvailableDocument = task.documents.some(
    (document) => document.status === "available",
  );
  const canComplete = !task.requires_document_upload || hasAvailableDocument;

  function requestHelp() {
    const reason = helpReason.trim();
    if (!reason) {
      setHelpError("Tell People Operations what you need help with.");
      return;
    }
    if (!task.can_update) return;
    setHelpError(null);
    onUpdate(task, "blocked", reason);
    setShowHelpForm(false);
    setHelpReason("");
  }

  function uploadFile(file: File | undefined) {
    if (!file || !task.can_update) return;
    setUploadError(null);
    uploadDocument.mutate({ taskId: task.id, file }, {
      onError: (error) => setUploadError(
        error instanceof Error
          ? error.message
          : "The file could not be uploaded. Please try again.",
      ),
    });
  }

  return (
    <li className="flex gap-4 px-4 py-5 sm:px-6">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-semibold text-gray-600">
        {position}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h3 className="font-medium text-gray-900">{task.title}</h3>
            {task.description && (
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-gray-600">
                {task.description}
              </p>
            )}
          </div>
          <span className={`w-fit shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${taskStatusStyle(task.status)}`}>
            {taskStatusLabels[task.status]}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500">
          <span>{task.responsible_party === "employee" ? "Your step" : "Workspace team step"}</span>
          <span>Due {formatDate(task.due_at)}</span>
          {task.completed_at && <span>Completed {formatDate(task.completed_at)}</span>}
        </div>
        {task.responsible_party === "employee" && task.resolution_note && (
          <p className="mt-3 whitespace-pre-wrap rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-950">
            <span className="font-semibold">People Operations response: </span>
            {task.resolution_note}
          </p>
        )}
        {task.responsible_party === "employee" && task.status === "blocked" && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
            <p className="text-sm font-medium text-amber-950">People Operations has been notified.</p>
            <p className="mt-1 text-sm text-amber-900">They’ll update this step when they’ve followed up.</p>
            {task.blocked_reason && (
              <p className="mt-2 whitespace-pre-wrap text-sm text-amber-900">
                <span className="font-medium">Your note: </span>{task.blocked_reason}
              </p>
            )}
          </div>
        )}
        {task.responsible_party === "employee" && task.requires_document_upload && (
          <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm font-semibold text-blue-950">Document required for this step</p>
            <p className="mt-1 text-sm text-blue-900">
              Upload a PDF or DOCX file up to 10 MB. MindHire scans it automatically before you can complete this step.
            </p>
            {task.documents.length > 0 && (
              <ul className="mt-3 space-y-2" aria-label="Uploaded task documents">
                {task.documents.map((document) => (
                  <li key={document.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-white px-3 py-2 text-sm">
                    <span className="min-w-0 truncate font-medium text-gray-800">{document.original_filename}</span>
                    <span className={`shrink-0 text-xs font-medium ${document.status === "available" ? "text-emerald-800" : document.status === "quarantined" || document.status === "rejected" ? "text-red-800" : "text-blue-800"}`}>
                      {document.status === "available"
                        ? "Scan complete"
                        : document.status === "quarantined"
                          ? "Blocked by security scan"
                          : document.status === "rejected"
                            ? "Upload could not be verified"
                            : document.status === "pending_upload"
                              ? "Upload not finished"
                              : document.status === "uploaded"
                                ? "Waiting for security scan"
                                : "Scanning…"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {task.can_update && !hasAvailableDocument && (
              <label className="mt-3 inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg bg-sr-text-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
                <span>{uploadDocument.isPending ? "Uploading and scanning…" : task.documents.some((document) => document.status === "pending_upload") ? "Retry upload" : task.documents.length > 0 ? "Upload another file" : "Choose file to upload"}</span>
                <input
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  disabled={uploadDocument.isPending}
                  onChange={(event) => {
                    uploadFile(event.currentTarget.files?.[0]);
                    event.currentTarget.value = "";
                  }}
                  className="sr-only"
                />
              </label>
            )}
            {uploadError && <p className="mt-2 text-sm text-red-800" role="alert">{uploadError}</p>}
          </div>
        )}
        {task.responsible_party === "employee" && (
          <OnboardingTaskActivity
            taskId={task.id}
            viewer="employee"
          />
        )}
        {task.responsible_party === "employee" && task.status !== "completed" && task.status !== "cancelled" && task.status !== "blocked" && (
          task.can_update ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {!showHelpForm && (
                <button
                  type="button"
                  disabled={updatePending || (task.status === "in_progress" && !canComplete)}
                  onClick={() => onUpdate(
                    task,
                    task.status === "not_started" ? "in_progress" : "completed",
                  )}
                  className="inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg bg-sr-text-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {updatePending
                    ? "Saving…"
                    : task.status === "not_started"
                      ? "Start this task"
                      : "Mark as complete"}
                </button>
              )}
              {task.status === "in_progress" && !canComplete && (
                <p className="w-full text-xs text-gray-600">
                  Upload the requested file and wait for the scan to finish before completing this step.
                </p>
              )}
              <button
                type="button"
                disabled={updatePending}
                onClick={() => {
                  setHelpError(null);
                  setShowHelpForm((visible) => !visible);
                }}
                className="inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {showHelpForm ? "Cancel" : "Need help?"}
              </button>
              {showHelpForm && (
                <div className="w-full rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-gray-700">
                      What do you need help with?
                    </span>
                    <textarea
                      required
                      maxLength={2000}
                      rows={3}
                      value={helpReason}
                      onChange={(event) => setHelpReason(event.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                    />
                  </label>
                  {helpError && <p className="mt-2 text-sm text-red-800" role="alert">{helpError}</p>}
                  <button
                    type="button"
                    disabled={updatePending || !helpReason.trim()}
                    onClick={requestHelp}
                    className="mt-3 inline-flex min-h-10 cursor-pointer items-center justify-center rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {updatePending ? "Sending…" : "Send to People Operations"}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-3 text-xs text-gray-500">
              {!planActive
                ? "This onboarding plan is not active. Contact People Operations if you need help."
                : blockedByEarlierStep
                  ? "This step will be available after the earlier onboarding steps are complete."
                  : "This step is currently unavailable. Contact People Operations for help."}
            </p>
          )
        )}
      </div>
    </li>
  );
}

export default function MyOnboardingPage() {
  const onboarding = useEmployeePortalOnboarding();
  const updateTask = useUpdateEmployeePortalTaskStatus();
  const [taskActionError, setTaskActionError] = useState<string | null>(null);

  function updateEmployeeTask(
    task: EmployeePortalTaskResponse,
    targetStatus: "in_progress" | "completed" | "blocked",
    blockedReason?: string,
  ) {
    if (!task.can_update) return;
    setTaskActionError(null);
    updateTask.mutate({
      taskId: task.id,
      request: {
        expected_version: task.version,
        target_status: targetStatus,
        blocked_reason: targetStatus === "blocked" ? blockedReason : null,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onError: () => setTaskActionError("We couldn’t update this step. Refresh the checklist and try again."),
    });
  }

  if (onboarding.isLoading) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">My onboarding</h1>
        <p className="mt-4 rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600" role="status">
          Loading your onboarding details…
        </p>
      </div>
    );
  }

  if (onboarding.isError) {
    const accountNotLinked = onboarding.error instanceof ApiError && onboarding.error.isNotFound;
    return (
      <div className="mx-auto w-full max-w-4xl">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">My onboarding</h1>
          <p className="mt-1 text-sm text-gray-600">Your new-hire information and onboarding checklist.</p>
        </header>
        <section className="mt-6 rounded-xl border border-gray-200 bg-white p-6 sm:p-8">
          <h2 className="font-semibold text-sr-text-blue">
            {accountNotLinked ? "No employee profile is linked to this account" : "We couldn’t load your onboarding"}
          </h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            {accountNotLinked
              ? "If you recently joined, ask your workspace’s People Operations team to link your account to your employee record."
              : "Your onboarding details are temporarily unavailable. Try again in a moment."}
          </p>
          {!accountNotLinked && (
            <button
              type="button"
              onClick={() => void onboarding.refetch()}
              className="mt-4 rounded-lg bg-sr-text-blue px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
            >
              Try again
            </button>
          )}
        </section>
      </div>
    );
  }

  const data = onboarding.data;
  if (!data) return null;

  const tasks = data.tasks;
  const completedTasks = tasks.filter((task) => task.status === "completed").length;
  const progress = tasks.length > 0 ? Math.round((completedTasks / tasks.length) * 100) : 0;
  const firstName = data.profile.full_name.trim().split(/\s+/)[0];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header>
        <p className="text-sm font-medium text-gray-500">Employee portal</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
          {firstName ? `Welcome, ${firstName}` : "My onboarding"}
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          View your employment details and follow the steps prepared for your first days.
        </p>
      </header>

      <section aria-labelledby="employee-summary-heading" className="rounded-xl border border-gray-200 bg-white p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 id="employee-summary-heading" className="text-lg font-semibold text-sr-text-blue">
              {data.profile.full_name}
            </h2>
            <p className="mt-1 text-sm text-gray-600">{data.profile.job_title}</p>
          </div>
          <span className="w-fit rounded-full bg-gray-100 px-3 py-1 text-xs font-medium capitalize text-gray-700">
            {data.profile.status.replaceAll("_", " ")}
          </span>
        </div>
        <dl className="mt-5 grid gap-4 border-t border-gray-100 pt-5 sm:grid-cols-2 lg:grid-cols-3">
          <ProfileField label="Work email" value={data.profile.work_email ?? "Not set"} />
          <ProfileField label="Department" value={data.profile.department ?? "Not set"} />
          <ProfileField label="Location" value={data.profile.location ?? "Not set"} />
          <ProfileField label="Start date" value={formatDate(data.profile.start_date)} />
        </dl>
      </section>

      <section aria-labelledby="checklist-heading" className="overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 id="checklist-heading" className="font-semibold text-sr-text-blue">Your onboarding checklist</h2>
              <p className="mt-1 text-sm text-gray-600">
                {data.started_at
                  ? `Started ${formatDate(data.started_at)}`
                  : "Your onboarding plan has not started yet."}
              </p>
            </div>
            {data.onboarding_status && (
              <span className="w-fit rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800">
                {planStatusLabels[data.onboarding_status]}
              </span>
            )}
          </div>
          {tasks.length > 0 && (
            <div className="mt-5">
              <div className="flex justify-between gap-3 text-xs text-gray-600">
                <span>{completedTasks} of {tasks.length} steps completed</span>
                <span>{progress}%</span>
              </div>
              <div
                className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100"
                role="progressbar"
                aria-label="Onboarding progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
              >
                <div className="h-full rounded-full bg-sr-green transition-[width]" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </div>
        {taskActionError && (
          <p className="border-b border-red-100 bg-red-50 px-5 py-3 text-sm text-red-800" role="alert">
            {taskActionError}
          </p>
        )}

        {data.onboarding_status === null ? (
          <div className="px-5 py-10 text-center sm:px-6">
            <h3 className="font-medium text-gray-900">Your plan is being prepared</h3>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-gray-600">
              People Operations will start your onboarding plan. Your checklist will appear here when it is ready.
            </p>
          </div>
        ) : tasks.length > 0 ? (
          <ol className="divide-y divide-gray-100">
            {tasks.map((task, index) => (
              <TaskItem
                key={task.id}
                task={task}
                position={index + 1}
                blockedByEarlierStep={tasks
                  .slice(0, index)
                  .some((earlierTask) => earlierTask.status !== "completed")}
                planActive={data.onboarding_status === "active"}
                updatePending={updateTask.isPending}
                onUpdate={updateEmployeeTask}
              />
            ))}
          </ol>
        ) : (
          <div className="px-5 py-10 text-center sm:px-6">
            <h3 className="font-medium text-gray-900">No checklist steps are available</h3>
            <p className="mt-2 text-sm text-gray-600">Contact People Operations for help with your onboarding plan.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-1 wrap-break-word text-sm text-gray-900">{value}</dd>
    </div>
  );
}
