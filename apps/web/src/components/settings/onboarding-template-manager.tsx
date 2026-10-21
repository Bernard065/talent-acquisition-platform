"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  useCreateOnboardingTemplate,
  useCreateOnboardingTemplateVersion,
  useDiscardOnboardingTemplateDraft,
  useOnboardingTemplateVersions,
  usePublishOnboardingTemplateDraft,
  useReactivateOnboardingTemplate,
  useRetireOnboardingTemplate,
  useUpdateOnboardingTemplateDraft,
} from "@/lib/api/hooks/onboarding";
import type {
  CreateOnboardingTemplateRequest,
  CreateOnboardingTemplateVersionRequest,
  OnboardingTemplateDraftActionRequest,
  OnboardingTemplateLifecycleActionRequest,
  OnboardingTemplateResponse,
  OnboardingTemplateTaskRequest,
  OnboardingTaskResponsibility,
  UpdateOnboardingTemplateDraftRequest,
} from "@/types/api/onboarding";
import type { Role } from "@/types/api/auth";
import { OnboardingTemplateVersionComparison } from "./onboarding-template-version-comparison";

type TemplateTaskDraft = {
  title: string;
  description: string;
  dueDays: string;
  assigneeRole: Role | "";
  responsibleParty: OnboardingTaskResponsibility;
  requiresDocumentUpload: boolean;
  requiresDocumentReview: boolean;
  prerequisitePositions: number[];
};
const blankTask = (): TemplateTaskDraft => ({
  title: "",
  description: "",
  dueDays: "",
  assigneeRole: "",
  responsibleParty: "workspace",
  requiresDocumentUpload: false,
  requiresDocumentReview: false,
  prerequisitePositions: [],
});

function taskRequestsFromVersion(
  template: OnboardingTemplateResponse,
): OnboardingTemplateTaskRequest[] {
  return [...template.tasks]
    .sort((left, right) => left.position - right.position)
    .map((task) => ({
      title: task.title,
      description: task.description,
      due_offset_days: task.due_offset_days,
      default_assignee_role: task.default_assignee_role,
      responsible_party: task.responsible_party,
      requires_document_upload: task.requires_document_upload,
      requires_document_review: task.requires_document_review,
      prerequisite_task_positions: [...task.prerequisite_task_positions],
    }));
}

const templateTimestampMonths = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatTemplateTimestamp(value: string | null | undefined): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = templateTimestampMonths[date.getUTCMonth()];
  const year = date.getUTCFullYear();
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hour}:${minute} UTC`;
}

function TemplateVersionProvenance({ template }: { template: OnboardingTemplateResponse }) {
  return (
    <div className="mt-2 space-y-1 text-xs text-gray-600">
      <p>
        Created {formatTemplateTimestamp(template.created_at)}
        {template.created_by_display_name ? ` by ${template.created_by_display_name}` : " · creator unavailable"}
      </p>
      {template.publication_status === "published" && (
        <p>
          {template.published_at
            ? `Published ${formatTemplateTimestamp(template.published_at)}`
            : "Publication date unavailable"}
          {template.published_by_display_name ? ` by ${template.published_by_display_name}` : " · publisher unavailable"}
        </p>
      )}
      {template.restored_from_version !== null && template.restored_from_version !== undefined ? (
        <p className="font-medium text-indigo-800">
          Restored from published version {template.restored_from_version}
          {template.based_on_version ? ` · draft created from version ${template.based_on_version}` : ""}
        </p>
      ) : template.based_on_version ? (
        <p>Draft created from published version {template.based_on_version}</p>
      ) : null}
    </div>
  );
}

function templateUsageHref(
  template: OnboardingTemplateResponse,
  status: "active" | "completed",
): string {
  const params = new URLSearchParams({
    template_id: template.id,
    template_name: template.name,
    template_version: String(template.version),
    status,
  });
  return `/dashboard/onboarding?${params.toString()}`;
}

function TemplateUsageCount({
  template,
  status,
  count,
  label,
}: {
  template: OnboardingTemplateResponse;
  status: "active" | "completed";
  count: number;
  label: string;
}) {
  const text = `${count} ${label}`;
  if (count === 0) return <span className="text-gray-500">{text}</span>;

  return (
    <Link
      href={templateUsageHref(template, status)}
      aria-label={`View ${count} ${label} onboarding plans using ${template.name}, version ${template.version}`}
      className="font-medium text-sr-text-blue underline-offset-2 hover:underline focus-visible:rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sr-green"
    >
      {text}
    </Link>
  );
}

function TemplateVersionUsage({ template }: { template: OnboardingTemplateResponse }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600">
      <span>Active and completed plans using this version:</span>
      <TemplateUsageCount
        template={template}
        status="active"
        count={template.active_onboarding_plan_count}
        label="in progress"
      />
      <TemplateUsageCount
        template={template}
        status="completed"
        count={template.completed_onboarding_plan_count}
        label="completed"
      />
    </div>
  );
}

export function OnboardingTemplateManager() {
  const templateVersions = useOnboardingTemplateVersions();
  const createTemplate = useCreateOnboardingTemplate();
  const createVersion = useCreateOnboardingTemplateVersion();
  const updateDraft = useUpdateOnboardingTemplateDraft();
  const publishDraft = usePublishOnboardingTemplateDraft();
  const discardDraft = useDiscardOnboardingTemplateDraft();
  const retireTemplate = useRetireOnboardingTemplate();
  const reactivateTemplate = useReactivateOnboardingTemplate();
  const [editingTemplate, setEditingTemplate] = useState<OnboardingTemplateResponse | null>(null);
  const [showEditorPreview, setShowEditorPreview] = useState(false);
  const [pendingDraftAction, setPendingDraftAction] = useState<{
    template: OnboardingTemplateResponse;
    action: "publish" | "discard";
  } | null>(null);
  const [pendingLifecycleAction, setPendingLifecycleAction] = useState<{
    template: OnboardingTemplateResponse;
    action: "retire" | "reactivate";
  } | null>(null);
  const [restoreFeedback, setRestoreFeedback] = useState<{
    sourceTemplateId: string;
    kind: "success" | "error";
    message: string;
  } | null>(null);
  const [name, setName] = useState("");
  const [tasks, setTasks] = useState<TemplateTaskDraft[]>([blankTask()]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const templateGroups = new Map<string, OnboardingTemplateResponse[]>();
  for (const template of templateVersions.data?.items ?? []) {
    const versions = templateGroups.get(template.name) ?? [];
    versions.push(template);
    templateGroups.set(template.name, versions);
  }

  function resetEditor() {
    setEditingTemplate(null);
    setName("");
    setTasks([blankTask()]);
    setShowEditorPreview(false);
  }

  function editTemplate(template: OnboardingTemplateResponse) {
    setEditingTemplate(template);
    setName(template.name);
    setTasks(template.tasks.map((task) => ({
      title: task.title,
      description: task.description ?? "",
      dueDays: task.due_offset_days?.toString() ?? "",
      assigneeRole: task.default_assignee_role ?? "",
      responsibleParty: task.responsible_party,
      requiresDocumentUpload: task.requires_document_upload,
      requiresDocumentReview: task.requires_document_review,
      prerequisitePositions: [...task.prerequisite_task_positions],
    })));
    setError(null);
    setMessage(null);
    setShowEditorPreview(false);
  }

  function taskRequests(): OnboardingTemplateTaskRequest[] {
    return tasks.map((task) => ({
      title: task.title.trim(),
      description: task.description.trim() || null,
      due_offset_days: task.dueDays === "" ? null : Number(task.dueDays),
      default_assignee_role:
        task.responsibleParty === "workspace" ? task.assigneeRole || null : null,
      responsible_party: task.responsibleParty,
      requires_document_upload: task.requiresDocumentUpload,
      requires_document_review: task.requiresDocumentReview,
      prerequisite_task_positions: task.prerequisitePositions,
    }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const serializedTasks = taskRequests();
    if (editingTemplate?.publication_status === "draft") {
      const request: UpdateOnboardingTemplateDraftRequest = {
        expected_revision: editingTemplate.draft_revision,
        tasks: serializedTasks,
      };
      updateDraft.mutate({
        templateId: editingTemplate.id,
        request,
        idempotencyKey: crypto.randomUUID(),
      }, {
        onSuccess: () => {
          const draftVersion = editingTemplate.version;
          resetEditor();
          setMessage(`Draft version ${draftVersion} saved. Review it, then publish when ready.`);
        },
        onError: () => setError("We couldn’t save this draft. It may have changed; refresh and try again."),
      });
      return;
    }

    if (editingTemplate) {
      createVersion.mutate({
        templateId: editingTemplate.id,
        request: {
          expected_version: editingTemplate.version,
          tasks: serializedTasks,
        },
        idempotencyKey: crypto.randomUUID(),
      }, {
        onSuccess: (draft) => {
          resetEditor();
          setMessage(`Draft version ${draft.version} saved. It will not be used for new hires until published.`);
        },
        onError: () => setError("We couldn’t save this draft. The template may have changed; refresh and try again."),
      });
      return;
    }

    const request: CreateOnboardingTemplateRequest = {
      name: name.trim(),
      version: 1,
      tasks: serializedTasks,
    };
    createTemplate.mutate({ request, idempotencyKey: crypto.randomUUID() }, {
      onSuccess: (draft) => {
        resetEditor();
        setMessage(`Draft version ${draft.version} saved. Preview and publish it before starting onboarding.`);
      },
      onError: () => setError("We couldn’t save the template draft. Check that its name is unique and try again."),
    });
  }

  function confirmDraftAction() {
    if (!pendingDraftAction) return;
    const { template, action } = pendingDraftAction;
    const request: OnboardingTemplateDraftActionRequest = {
      expected_revision: template.draft_revision,
    };
    setError(null);
    if (action === "publish") {
      publishDraft.mutate({
        templateId: template.id,
        request,
        idempotencyKey: crypto.randomUUID(),
      }, {
        onSuccess: (published) => {
          setPendingDraftAction(null);
          setMessage(`Version ${published.version} is published and will be used for new hires. Existing plans are unchanged.`);
        },
        onError: () => {
          setPendingDraftAction(null);
          setError("We couldn’t publish this draft. Refresh the template list and try again.");
        },
      });
      return;
    }

    discardDraft.mutate({
      templateId: template.id,
      request,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setPendingDraftAction(null);
        setMessage(`Draft version ${template.version} was discarded.`);
      },
      onError: () => {
        setPendingDraftAction(null);
        setError("We couldn’t discard this draft. Refresh the template list and try again.");
      },
    });
  }

  function confirmLifecycleAction() {
    if (!pendingLifecycleAction) return;
    const { template, action } = pendingLifecycleAction;
    const request: OnboardingTemplateLifecycleActionRequest = {
      expected_version: template.version,
    };
    setError(null);
    const mutation = action === "retire" ? retireTemplate : reactivateTemplate;
    mutation.mutate({
      templateId: template.id,
      request,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: (updated) => {
        setPendingLifecycleAction(null);
        setMessage(action === "retire"
          ? `${updated.name} version ${updated.version} was retired. Existing onboarding plans are unchanged.`
          : `${updated.name} version ${updated.version} is available for future hires again. Existing onboarding plans are unchanged.`);
      },
      onError: () => {
        setPendingLifecycleAction(null);
        setError(action === "retire"
          ? "We couldn’t retire this template. Refresh the template list and resolve any draft before trying again."
          : "We couldn’t reactivate this template. Refresh the template list and try again.");
      },
    });
  }

  function createDraftFromPreviousVersion(
    current: OnboardingTemplateResponse,
    source: OnboardingTemplateResponse,
  ) {
    setRestoreFeedback(null);
    const request: CreateOnboardingTemplateVersionRequest = {
      expected_version: current.version,
      restore_from_template_id: source.id,
      tasks: taskRequestsFromVersion(source),
    };
    createVersion.mutate({
      templateId: current.id,
      request,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: (draft) => setRestoreFeedback({
        sourceTemplateId: source.id,
        kind: "success",
        message: `Draft version ${draft.version} was created from published version ${source.version}. Review the comparison, edit if needed, then publish when ready.`,
      }),
      onError: () => setRestoreFeedback({
        sourceTemplateId: source.id,
        kind: "error",
        message: "We couldn’t create a draft from this version. The published template may have changed; refresh and try again.",
      }),
    });
  }

  const templateMutationPending =
    createTemplate.isPending || createVersion.isPending || updateDraft.isPending ||
    publishDraft.isPending || discardDraft.isPending || retireTemplate.isPending ||
    reactivateTemplate.isPending;

  function removeTask(indexToRemove: number) {
    const removedPosition = indexToRemove + 1;
    setTasks((current) =>
      current
        .filter((_, index) => index !== indexToRemove)
        .map((task) => ({
          ...task,
          prerequisitePositions: task.prerequisitePositions
            .filter((position) => position !== removedPosition)
            .map((position) => position > removedPosition ? position - 1 : position),
        })),
    );
  }

  return (
    <section className="max-w-4xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h2 className="text-lg font-semibold text-sr-text-blue">Onboarding templates</h2>
        <p className="mt-1 text-sm leading-relaxed text-gray-600">
          Save changes as a draft, preview the employee checklist, then publish when it is ready. Retire templates you no longer want offered to new hires. Existing onboarding plans keep their original template version.
        </p>
      </div>

      {templateVersions.isLoading ? (
        <p className="mt-6 text-sm text-gray-600" role="status">Loading templates…</p>
      ) : templateVersions.isError ? (
        <p className="mt-6 text-sm text-red-800" role="alert">We couldn’t load onboarding template history. Refresh and try again.</p>
      ) : templateGroups.size ? (
        <ul className="mt-5 grid gap-3 sm:grid-cols-2">
          {Array.from(templateGroups.entries()).map(([templateName, versions]) => {
            const publishedVersions = versions.filter(
              (template) => template.publication_status === "published",
            );
            const current = publishedVersions.find((template) => template.is_active) ?? null;
            const latestPublished = publishedVersions[0] ?? null;
            const retired = latestPublished !== null && current === null;
            const primaryPublished = current ?? latestPublished;
            const draft = versions.find(
              (template) => template.publication_status === "draft",
            ) ?? null;
            const previous = publishedVersions.filter(
              (template) => template.id !== primaryPublished?.id,
            );
            const displayedTemplate = primaryPublished ?? draft;
            if (!displayedTemplate) return null;
            return (
              <li key={templateName} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-gray-900">{templateName}</p>
                    <p className="mt-1 text-sm text-gray-600">
                      {primaryPublished
                        ? `Published version ${primaryPublished.version} · ${primaryPublished.tasks.length} tasks`
                        : `Draft version ${displayedTemplate.version} · ${displayedTemplate.tasks.length} tasks`}
                    </p>
                    <span className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${current ? "bg-emerald-50 text-emerald-800" : retired ? "bg-gray-100 text-gray-800" : "bg-amber-50 text-amber-900"}`}>
                      {current ? "Active · Used for new hires" : retired ? "Retired · Not used for new hires" : "Draft · Not used for new hires"}
                    </span>
                    {primaryPublished && <TemplateVersionProvenance template={primaryPublished} />}
                    {primaryPublished && <TemplateVersionUsage template={primaryPublished} />}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {current && !draft && (
                      <>
                        <button
                          type="button"
                          onClick={() => editTemplate(current)}
                          className="min-h-10 cursor-pointer rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                        >
                          Create draft version
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingLifecycleAction({ template: current, action: "retire" })}
                          disabled={templateMutationPending || Boolean(editingTemplate)}
                          className="min-h-10 cursor-pointer rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Retire template
                        </button>
                      </>
                    )}
                    {retired && !draft && primaryPublished && (
                      <button
                        type="button"
                        onClick={() => setPendingLifecycleAction({ template: primaryPublished, action: "reactivate" })}
                        disabled={templateMutationPending || Boolean(editingTemplate)}
                        className="min-h-10 cursor-pointer rounded-lg border border-emerald-300 px-3 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Reactivate template
                      </button>
                    )}
                  </div>
                </div>
                {current && draft && (
                  <p className="mt-3 rounded-md bg-gray-50 p-3 text-xs text-gray-700">
                    Publish or discard draft version {draft.version} before retiring this template.
                  </p>
                )}
                {pendingLifecycleAction?.template.id === primaryPublished?.id && (
                  <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3" role="group" aria-label="Confirm template lifecycle action">
                    <p className="text-sm font-medium text-gray-900">
                      {pendingLifecycleAction.action === "retire"
                        ? `Retire ${templateName} version ${primaryPublished.version}?`
                        : `Reactivate ${templateName} version ${primaryPublished.version}?`}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-gray-700">
                      {pendingLifecycleAction.action === "retire"
                        ? `This removes the template from choices for future hires. ${primaryPublished.active_onboarding_plan_count} in-progress ${primaryPublished.active_onboarding_plan_count === 1 ? "plan uses" : "plans use"} this version; those plans and their checklists will remain unchanged.`
                        : "This makes the latest published version available for future hires again. Existing onboarding plans and their checklists remain unchanged."}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={confirmLifecycleAction}
                        disabled={templateMutationPending}
                        className="min-h-9 cursor-pointer rounded-md bg-sr-text-blue px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {templateMutationPending ? "Working…" : pendingLifecycleAction.action === "retire" ? "Confirm retirement" : "Confirm reactivation"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setPendingLifecycleAction(null)}
                        disabled={templateMutationPending}
                        className="min-h-9 cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {primaryPublished && (
                  <ol className="mt-4 space-y-1 text-sm text-gray-700">
                    {primaryPublished.tasks.map((task, index) => {
                    const prerequisiteTitles = task.prerequisite_task_positions
                      .map((position) => primaryPublished.tasks[position - 1]?.title)
                      .filter((title): title is string => Boolean(title));
                    return (
                      <li key={task.id}>
                        {index + 1}. {task.title} · {task.responsible_party === "employee" ? "Employee" : "Workspace team"}
                        {task.requires_document_upload ? " · File upload required" : ""}
                        {task.requires_document_review ? " · People Ops review required" : ""}
                        {prerequisiteTitles.length > 0 && (
                          <span className="block pl-4 text-xs text-gray-500">
                            After: {prerequisiteTitles.join(", ")}
                          </span>
                        )}
                      </li>
                    );
                    })}
                  </ol>
                )}
                {draft && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-amber-950">
                          Draft version {draft.version}
                        </p>
                        <p className="mt-1 text-xs text-amber-900">
                          Employee checklist preview. Publishing makes this version available for future hires.
                        </p>
                        <TemplateVersionProvenance template={draft} />
                      </div>
                      <button
                        type="button"
                        onClick={() => editTemplate(draft)}
                        className="min-h-9 cursor-pointer rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-950 hover:bg-amber-100"
                      >
                        Edit draft
                      </button>
                    </div>
                    {primaryPublished && <OnboardingTemplateVersionComparison current={primaryPublished} draft={draft} />}
                    <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-amber-950">
                      {draft.tasks.map((task) => {
                        const prerequisiteTitles = task.prerequisite_task_positions
                          .map((position) => draft.tasks[position - 1]?.title)
                          .filter((title): title is string => Boolean(title));
                        return (
                          <li key={task.id}>
                            <span className="font-medium">{task.title}</span>
                            {task.description && <p className="text-xs text-amber-900">{task.description}</p>}
                            <p className="text-xs text-amber-900">
                              {task.responsible_party === "employee" ? "Employee task" : "Workspace team task"}
                              {task.due_offset_days !== null ? ` · Due ${task.due_offset_days} days after onboarding starts` : ""}
                              {task.requires_document_upload ? " · File upload required" : ""}
                              {task.requires_document_review ? " · Review required" : ""}
                            </p>
                            {prerequisiteTitles.length > 0 && (
                              <p className="text-xs text-amber-900">
                                Available after: {prerequisiteTitles.join(", ")}
                              </p>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                    {pendingDraftAction?.template.id === draft.id ? (
                      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-amber-200 pt-3" role="group" aria-label="Confirm draft action">
                        <p className="mr-2 text-sm text-amber-950">
                          {pendingDraftAction.action === "publish"
                            ? `Publish version ${draft.version} for future hires?`
                            : `Discard draft version ${draft.version}? This cannot be undone.`}
                        </p>
                        <button
                          type="button"
                          onClick={confirmDraftAction}
                          disabled={templateMutationPending}
                          className="min-h-9 cursor-pointer rounded-md bg-sr-text-blue px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {templateMutationPending ? "Working…" : pendingDraftAction.action === "publish" ? "Confirm publish" : "Confirm discard"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingDraftAction(null)}
                          disabled={templateMutationPending}
                          className="min-h-9 cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="mt-4 flex flex-wrap gap-2 border-t border-amber-200 pt-3">
                        {editingTemplate?.id === draft.id && (
                          <p className="w-full text-xs text-amber-900">
                            Save or cancel your draft edits before publishing or discarding this version.
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={() => setPendingDraftAction({ template: draft, action: "publish" })}
                          disabled={templateMutationPending || editingTemplate?.id === draft.id}
                          className="min-h-9 cursor-pointer rounded-md bg-sr-text-blue px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Publish draft
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingDraftAction({ template: draft, action: "discard" })}
                          disabled={templateMutationPending || editingTemplate?.id === draft.id}
                          className="min-h-9 cursor-pointer rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Discard draft
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {previous.length > 0 && (
                  <details className="mt-4 border-t border-gray-100 pt-3">
                    <summary className="cursor-pointer text-sm font-medium text-gray-700">
                      Previous versions ({previous.length})
                    </summary>
                    <ul className="mt-3 space-y-3">
                      {previous.map((template) => (
                        <li key={template.id} className="rounded-md bg-gray-50 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-medium text-gray-700">
                              Version {template.version} · Previous version
                            </p>
                            {current && (
                              <button
                                type="button"
                                onClick={() => createDraftFromPreviousVersion(current, template)}
                                disabled={templateMutationPending || Boolean(draft) || Boolean(editingTemplate)}
                                aria-label={`Use published version ${template.version} as a new draft`}
                                className="min-h-9 cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {createVersion.isPending ? "Creating draft…" : "Use as new draft"}
                              </button>
                            )}
                          </div>
                          <TemplateVersionProvenance template={template} />
                          <TemplateVersionUsage template={template} />
                          {draft ? (
                            <p className="mt-2 text-xs text-gray-600">
                              Publish or discard draft version {draft.version} before restoring another version.
                            </p>
                          ) : editingTemplate ? (
                            <p className="mt-2 text-xs text-gray-600">
                              Save or cancel the open template editor before restoring a previous version.
                            </p>
                          ) : null}
                          {restoreFeedback?.sourceTemplateId === template.id && (
                            <p
                              className={`mt-2 text-xs ${restoreFeedback.kind === "error" ? "text-red-800" : "text-emerald-800"}`}
                              role={restoreFeedback.kind === "error" ? "alert" : "status"}
                            >
                              {restoreFeedback.message}
                            </p>
                          )}
                          <ol className="mt-2 space-y-1 text-xs text-gray-600">
                            {[...template.tasks]
                              .sort((left, right) => left.position - right.position)
                              .map((task, index) => (
                                <li key={task.id}>{index + 1}. {task.title}</li>
                              ))}
                          </ol>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
          No onboarding templates yet. Save a template draft, review its employee checklist, and publish it before starting onboarding.
        </p>
      )}

      <form className="mt-7 space-y-5 border-t border-gray-100 pt-6" onSubmit={submit}>
        <h3 className="font-semibold text-gray-900">
          {editingTemplate?.publication_status === "draft"
            ? `Edit draft version ${editingTemplate.version}`
            : editingTemplate
              ? `Prepare draft version ${editingTemplate.version + 1}`
              : "Create a template draft"}
        </h3>
        {editingTemplate ? (
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm text-blue-950">
            <p className="font-medium">
              {editingTemplate.name} · {editingTemplate.publication_status === "draft" ? `Draft version ${editingTemplate.version}` : `Published version ${editingTemplate.version}`}
            </p>
            <p className="mt-1">
              {editingTemplate.publication_status === "draft"
                ? "Saving updates this draft only. Preview it and publish when it is ready."
                : `Saving creates draft version ${editingTemplate.version + 1}. The current published version stays in use until you publish the draft.`}
            </p>
          </div>
        ) : (
          <label className="block max-w-xl">
            <span className="mb-1 block text-sm font-medium text-gray-700">Template name</span>
            <input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="New employee onboarding" />
          </label>
        )}
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Add tasks in a clear display order, then select only the tasks that must be finished first. Leave prerequisites empty when a task can start at any time.</p>
          {tasks.map((task, index) => (
            <fieldset key={index} className="grid gap-3 rounded-lg border border-gray-200 p-4 sm:grid-cols-2">
              <legend className="px-1 text-sm font-medium text-gray-700">Task {index + 1}</legend>
              <label className="sm:col-span-2">
                <span className="mb-1 block text-sm text-gray-700">Task title</span>
                <input required maxLength={200} value={task.title} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" placeholder="Prepare equipment and accounts" />
              </label>
              <label>
                <span className="mb-1 block text-sm text-gray-700">Description (optional)</span>
                <input maxLength={5000} value={task.description} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
              </label>
              <label>
                <span className="mb-1 block text-sm text-gray-700">Due after start (days)</span>
                <input type="number" min={0} value={task.dueDays} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, dueDays: event.target.value } : item))} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" placeholder="No due date" />
              </label>
              <label>
                <span className="mb-1 block text-sm text-gray-700">Who is responsible?</span>
                <select value={task.responsibleParty} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, responsibleParty: event.target.value as OnboardingTaskResponsibility, assigneeRole: "", requiresDocumentUpload: event.target.value === "employee" ? item.requiresDocumentUpload : false, requiresDocumentReview: event.target.value === "employee" ? item.requiresDocumentReview : false } : item))} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                  <option value="workspace">Workspace team</option>
                  <option value="employee">Employee</option>
                </select>
              </label>
              {task.responsibleParty === "employee" && (
                <label className="flex items-start gap-2 sm:col-span-2">
                  <input
                    type="checkbox"
                    checked={task.requiresDocumentUpload}
                    onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, requiresDocumentUpload: event.target.checked, requiresDocumentReview: event.target.checked ? item.requiresDocumentReview : false } : item))}
                    className="mt-0.5 h-4 w-4 cursor-pointer rounded border-gray-300 text-sr-green focus:ring-sr-green"
                  />
                  <span className="text-sm text-gray-700">
                    Require the employee to upload a file before completing this task
                  </span>
                </label>
              )}
              {task.responsibleParty === "employee" && task.requiresDocumentUpload && (
                <label className="flex items-start gap-2 sm:col-span-2">
                  <input
                    type="checkbox"
                    checked={task.requiresDocumentReview}
                    onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, requiresDocumentReview: event.target.checked } : item))}
                    className="mt-0.5 h-4 w-4 cursor-pointer rounded border-gray-300 text-sr-green focus:ring-sr-green"
                  />
                  <span className="text-sm text-gray-700">
                    Require People Operations to accept the document before the employee can complete this task
                  </span>
                </label>
              )}
              {task.responsibleParty === "workspace" && (
                <label>
                  <span className="mb-1 block text-sm text-gray-700">Default assignee role (optional)</span>
                  <select value={task.assigneeRole} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, assigneeRole: event.target.value as Role | "" } : item))} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                    <option value="">Assign later</option>
                    <option value="people_operations">People Ops</option>
                    <option value="tenant_admin">Workspace admin</option>
                    <option value="recruiter">Recruiter</option>
                    <option value="hiring_manager">Hiring manager</option>
                  </select>
                </label>
              )}
              <details className="rounded-lg border border-gray-100 bg-gray-50 p-3 sm:col-span-2">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  Prerequisites {task.prerequisitePositions.length > 0 ? `(${task.prerequisitePositions.length} selected)` : "(none)"}
                </summary>
                {index === 0 ? (
                  <p className="mt-2 text-xs text-gray-500">The first task has no earlier tasks to wait for.</p>
                ) : (
                  <fieldset className="mt-3 space-y-2">
                    <legend className="mb-2 text-xs text-gray-600">
                      Select the tasks that must be completed before this task unlocks.
                    </legend>
                    {tasks.slice(0, index).map((previousTask, previousIndex) => {
                      const prerequisitePosition = previousIndex + 1;
                      return (
                        <label key={prerequisitePosition} className="flex items-start gap-2 text-sm text-gray-700">
                          <input
                            type="checkbox"
                            checked={task.prerequisitePositions.includes(prerequisitePosition)}
                            onChange={(event) => setTasks((current) => current.map((item, itemIndex) => {
                              if (itemIndex !== index) return item;
                              const positions = new Set(item.prerequisitePositions);
                              if (event.target.checked) positions.add(prerequisitePosition);
                              else positions.delete(prerequisitePosition);
                              return { ...item, prerequisitePositions: [...positions].sort((a, b) => a - b) };
                            }))}
                            className="mt-0.5 h-4 w-4 cursor-pointer rounded border-gray-300 text-sr-green focus:ring-sr-green"
                          />
                          <span>{previousTask.title.trim() || `Task ${prerequisitePosition}`}</span>
                        </label>
                      );
                    })}
                  </fieldset>
                )}
              </details>
              {tasks.length > 1 && <button type="button" className="justify-self-start text-sm font-medium text-red-700 underline" onClick={() => removeTask(index)}>Remove task</button>}
            </fieldset>
          ))}
          <button type="button" disabled={tasks.length >= 100} onClick={() => setTasks((current) => [...current, blankTask()])} className="text-sm font-medium text-sr-text-blue underline disabled:opacity-50">Add task</button>
        </div>
        <div>
          <button
            type="button"
            onClick={() => setShowEditorPreview((visible) => !visible)}
            className="min-h-10 cursor-pointer rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {showEditorPreview ? "Hide employee checklist preview" : "Preview employee checklist"}
          </button>
          {showEditorPreview && (
            <section className="mt-3 rounded-lg border border-blue-100 bg-blue-50 p-4" aria-label="Employee checklist preview">
              <h4 className="font-semibold text-blue-950">Employee checklist preview</h4>
              <p className="mt-1 text-sm text-blue-900">
                {name.trim() || editingTemplate?.name || "New onboarding template"} · {editingTemplate?.publication_status === "draft" ? `Draft version ${editingTemplate.version}` : `Version ${(editingTemplate?.version ?? 0) + 1}`}
              </p>
              <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm text-blue-950">
                {tasks.map((task, index) => {
                  const prerequisiteTitles = task.prerequisitePositions
                    .map((position) => tasks[position - 1]?.title.trim())
                    .filter((title): title is string => Boolean(title));
                  return (
                    <li key={`preview-${index}`}>
                      <span className="font-medium">{task.title.trim() || `Task ${index + 1}`}</span>
                      {task.description.trim() && <p className="text-blue-900">{task.description.trim()}</p>}
                      <p className="text-xs text-blue-900">
                        {task.responsibleParty === "employee" ? "Employee task" : "Workspace team task"}
                        {task.dueDays !== "" ? ` · Due ${task.dueDays} days after onboarding starts` : ""}
                        {task.requiresDocumentUpload ? " · File upload required" : ""}
                        {task.requiresDocumentReview ? " · Review required" : ""}
                      </p>
                      {prerequisiteTitles.length > 0 && (
                        <p className="text-xs text-blue-900">Available after: {prerequisiteTitles.join(", ")}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>
          )}
        </div>
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-800">{message}</p>}
        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={templateMutationPending}
            className="min-h-10 cursor-pointer rounded-lg bg-sr-text-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {templateMutationPending
              ? "Saving…"
              : editingTemplate?.publication_status === "draft"
                ? "Save draft changes"
                : editingTemplate
                  ? `Save draft version ${editingTemplate.version + 1}`
                  : "Save as draft"}
          </button>
          {editingTemplate && (
            <button
              type="button"
              onClick={resetEditor}
              disabled={templateMutationPending}
              className="min-h-10 cursor-pointer rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
