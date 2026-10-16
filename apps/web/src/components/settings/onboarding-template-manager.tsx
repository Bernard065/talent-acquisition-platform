"use client";

import { useState, type FormEvent } from "react";
import { useCreateOnboardingTemplate, useOnboardingTemplates } from "@/lib/api/hooks/onboarding";
import type { CreateOnboardingTemplateRequest } from "@/types/api/onboarding";
import type { Role } from "@/types/api/auth";

type TemplateTaskDraft = { title: string; description: string; dueDays: string; assigneeRole: Role | "" };
const blankTask = (): TemplateTaskDraft => ({ title: "", description: "", dueDays: "", assigneeRole: "" });

export function OnboardingTemplateManager() {
  const templates = useOnboardingTemplates();
  const createTemplate = useCreateOnboardingTemplate();
  const [name, setName] = useState("");
  const [tasks, setTasks] = useState<TemplateTaskDraft[]>([blankTask()]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const request: CreateOnboardingTemplateRequest = {
      name: name.trim(),
      version: 1,
      tasks: tasks.map((task) => ({
        title: task.title.trim(),
        description: task.description.trim() || null,
        due_offset_days: task.dueDays === "" ? null : Number(task.dueDays),
        default_assignee_role: task.assigneeRole || null,
      })),
    };
    createTemplate.mutate({ request, idempotencyKey: crypto.randomUUID() }, {
      onSuccess: () => {
        setName("");
        setTasks([blankTask()]);
        setMessage("Onboarding template created.");
      },
      onError: () => setError("We couldn’t create the template. Check that its name is unique and try again."),
    });
  }

  return (
    <section className="max-w-4xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h2 className="text-lg font-semibold text-sr-text-blue">Onboarding templates</h2>
        <p className="mt-1 text-sm leading-relaxed text-gray-600">
          Define reusable tasks for new hires in the order they should be completed. A template is snapshotted when onboarding starts, so later changes won’t alter active plans.
        </p>
      </div>

      {templates.isLoading ? (
        <p className="mt-6 text-sm text-gray-600" role="status">Loading templates…</p>
      ) : templates.isError ? (
        <p className="mt-6 text-sm text-red-800" role="alert">We couldn’t load onboarding templates. Refresh and try again.</p>
      ) : templates.data?.items.length ? (
        <ul className="mt-5 grid gap-3 sm:grid-cols-2">
          {templates.data.items.map((template) => (
            <li key={template.id} className="rounded-lg border border-gray-200 p-4">
              <p className="font-medium text-gray-900">{template.name}</p>
              <p className="mt-1 text-sm text-gray-600">Version {template.version} · {template.tasks.length} tasks</p>
              <ol className="mt-3 space-y-1 text-sm text-gray-700">
                {template.tasks.map((task, index) => <li key={task.id}>{index + 1}. {task.title}</li>)}
              </ol>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
          No active templates yet. Create one below before starting onboarding for a hired candidate.
        </p>
      )}

      <form className="mt-7 space-y-5 border-t border-gray-100 pt-6" onSubmit={submit}>
        <h3 className="font-semibold text-gray-900">Create a template</h3>
        <label className="block max-w-xl">
          <span className="mb-1 block text-sm font-medium text-gray-700">Template name</span>
          <input required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="New employee onboarding" />
        </label>
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Add tasks from first to last. New hires must complete them in this order.</p>
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
              <label className="sm:col-span-2">
                <span className="mb-1 block text-sm text-gray-700">Default assignee role (optional)</span>
                <select value={task.assigneeRole} onChange={(event) => setTasks((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, assigneeRole: event.target.value as Role | "" } : item))} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                  <option value="">Assign later</option>
                  <option value="people_operations">People Ops</option>
                  <option value="tenant_admin">Workspace admin</option>
                  <option value="recruiter">Recruiter</option>
                  <option value="hiring_manager">Hiring manager</option>
                </select>
              </label>
              {tasks.length > 1 && <button type="button" className="justify-self-start text-sm font-medium text-red-700 underline" onClick={() => setTasks((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove task</button>}
            </fieldset>
          ))}
          <button type="button" disabled={tasks.length >= 100} onClick={() => setTasks((current) => [...current, blankTask()])} className="text-sm font-medium text-sr-text-blue underline disabled:opacity-50">Add task</button>
        </div>
        {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-800">{message}</p>}
        <button type="submit" disabled={createTemplate.isPending} className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
          {createTemplate.isPending ? "Creating…" : "Create template"}
        </button>
      </form>
    </section>
  );
}
