"use client";

import { useState, type FormEvent } from "react";
import {
  useCreateOnboardingTemplate,
  useCreateOnboardingTemplateVersion,
  useOnboardingTemplateVersions,
} from "@/lib/api/hooks/onboarding";
import type {
  CreateOnboardingTemplateRequest,
  OnboardingTemplateResponse,
  OnboardingTemplateTaskRequest,
  OnboardingTaskResponsibility,
} from "@/types/api/onboarding";
import type { Role } from "@/types/api/auth";

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

export function OnboardingTemplateManager() {
  const templateVersions = useOnboardingTemplateVersions();
  const createTemplate = useCreateOnboardingTemplate();
  const createVersion = useCreateOnboardingTemplateVersion();
  const [editingTemplate, setEditingTemplate] = useState<OnboardingTemplateResponse | null>(null);
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
  }

  function editAsNewVersion(template: OnboardingTemplateResponse) {
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
    if (editingTemplate) {
      createVersion.mutate({
        templateId: editingTemplate.id,
        request: {
          expected_version: editingTemplate.version,
          tasks: serializedTasks,
        },
        idempotencyKey: crypto.randomUUID(),
      }, {
        onSuccess: () => {
          const nextVersion = editingTemplate.version + 1;
          resetEditor();
          setMessage(`Version ${nextVersion} published. Existing onboarding plans are unchanged.`);
        },
        onError: () => setError("We couldn’t publish this version. The template may have changed; refresh and try again."),
      });
      return;
    }

    const request: CreateOnboardingTemplateRequest = {
      name: name.trim(),
      version: 1,
      tasks: serializedTasks,
    };
    createTemplate.mutate({ request, idempotencyKey: crypto.randomUUID() }, {
      onSuccess: () => {
        resetEditor();
        setMessage("Onboarding template created.");
      },
      onError: () => setError("We couldn’t create the template. Check that its name is unique and try again."),
    });
  }

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
          Define reusable tasks for new hires. Add prerequisites only when one task must wait for another; tasks without prerequisites can be done in parallel. A template is snapshotted when onboarding starts, so later changes won’t alter active plans.
        </p>
      </div>

      {templateVersions.isLoading ? (
        <p className="mt-6 text-sm text-gray-600" role="status">Loading templates…</p>
      ) : templateVersions.isError ? (
        <p className="mt-6 text-sm text-red-800" role="alert">We couldn’t load onboarding template history. Refresh and try again.</p>
      ) : templateGroups.size ? (
        <ul className="mt-5 grid gap-3 sm:grid-cols-2">
          {Array.from(templateGroups.entries()).map(([templateName, versions]) => {
            const current = versions.find((template) => template.is_active) ?? versions[0];
            if (!current) return null;
            const previous = versions.filter((template) => template.id !== current.id);
            return (
              <li key={templateName} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-gray-900">{templateName}</p>
                    <p className="mt-1 text-sm text-gray-600">
                      Current version {current.version} · {current.tasks.length} tasks
                    </p>
                    <span className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${current.is_active ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>
                      {current.is_active ? "Used for new hires" : "No active version"}
                    </span>
                  </div>
                  {current.is_active && (
                    <button
                      type="button"
                      onClick={() => editAsNewVersion(current)}
                      className="min-h-10 cursor-pointer rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Create new version
                    </button>
                  )}
                </div>
                <ol className="mt-4 space-y-1 text-sm text-gray-700">
                  {current.tasks.map((task, index) => {
                    const prerequisiteTitles = task.prerequisite_task_positions
                      .map((position) => current.tasks[position - 1]?.title)
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
                {previous.length > 0 && (
                  <details className="mt-4 border-t border-gray-100 pt-3">
                    <summary className="cursor-pointer text-sm font-medium text-gray-700">
                      Previous versions ({previous.length})
                    </summary>
                    <ul className="mt-3 space-y-3">
                      {previous.map((template) => (
                        <li key={template.id} className="rounded-md bg-gray-50 p-3">
                          <p className="text-sm font-medium text-gray-700">
                            Version {template.version} · Previous version
                          </p>
                          <ol className="mt-2 space-y-1 text-xs text-gray-600">
                            {template.tasks.map((task, index) => (
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
          No onboarding templates yet. Create one below before starting onboarding for a hired candidate.
        </p>
      )}

      <form className="mt-7 space-y-5 border-t border-gray-100 pt-6" onSubmit={submit}>
        <h3 className="font-semibold text-gray-900">
          {editingTemplate ? `Create version ${editingTemplate.version + 1}` : "Create a template"}
        </h3>
        {editingTemplate ? (
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm text-blue-950">
            <p className="font-medium">{editingTemplate.name} · Current version {editingTemplate.version}</p>
            <p className="mt-1">
              Publishing creates version {editingTemplate.version + 1} for future hires. Existing onboarding plans keep version {editingTemplate.version}.
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
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-800">{message}</p>}
        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={createTemplate.isPending || createVersion.isPending}
            className="min-h-10 cursor-pointer rounded-lg bg-sr-text-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {createTemplate.isPending || createVersion.isPending
              ? "Saving…"
              : editingTemplate
                ? `Publish version ${editingTemplate.version + 1}`
                : "Create template"}
          </button>
          {editingTemplate && (
            <button
              type="button"
              onClick={resetEditor}
              disabled={createVersion.isPending}
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
