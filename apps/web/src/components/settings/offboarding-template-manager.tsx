"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import {
  useOffboardingTemplate,
  useReplaceOffboardingTemplate,
} from "@/lib/api/hooks/employee-records";
import type {
  OffboardingTemplateTask,
  ReplaceOffboardingTemplateRequest,
} from "@/types/api/employee-records";

const starterTasks: OffboardingTemplateTask[] = [
  {
    title: "Transfer responsibilities and document handover",
    description: "Agree on handover coverage and share outstanding work.",
    due_days_before_last_working_day: 3,
  },
  {
    title: "Complete an exit interview",
    description: "Capture feedback and any follow-up needed after departure.",
    due_days_before_last_working_day: 2,
  },
  {
    title: "Collect company equipment",
    description: "Record returned equipment and any items still outstanding.",
    due_days_before_last_working_day: 0,
  },
  {
    title: "Confirm final pay and benefits handover",
    description: "Coordinate final payroll and benefits information with People Operations.",
    due_days_before_last_working_day: 0,
  },
];

function copyTask(task: OffboardingTemplateTask): OffboardingTemplateTask {
  return {
    title: task.title,
    description: task.description ?? "",
    due_days_before_last_working_day: task.due_days_before_last_working_day,
  };
}

export function OffboardingTemplateManager() {
  const template = useOffboardingTemplate();
  const saveTemplate = useReplaceOffboardingTemplate();
  const [draft, setDraft] = useState<OffboardingTemplateTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const items = draft ?? (
    template.data?.items.length
      ? template.data.items.map(copyTask)
      : starterTasks.map(copyTask)
  );

  function updateTask(index: number, changes: Partial<OffboardingTemplateTask>) {
    setDraft(items.map((task, taskIndex) =>
      taskIndex === index ? { ...task, ...changes } : task,
    ));
    setError(null);
    setSaved(false);
  }

  function save() {
    const request: ReplaceOffboardingTemplateRequest = {
      items: items.map((task) => ({
        title: task.title.trim(),
        description: task.description?.trim() || null,
        due_days_before_last_working_day: task.due_days_before_last_working_day,
      })),
    };
    if (request.items.some((task) => !task.title)) {
      setError("Give each checklist task a title before saving.");
      return;
    }

    setError(null);
    setSaved(false);
    saveTemplate.mutate(request, {
      onSuccess: () => {
        setDraft(null);
        setSaved(true);
      },
      onError: (cause) => {
        setError(cause instanceof ApiError
          ? cause.detail
          : "The offboarding checklist could not be saved. Try again.");
      },
    });
  }

  if (template.isLoading) {
    return <p className="py-8 text-sm text-gray-600">Loading the offboarding checklist…</p>;
  }
  if (template.isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <p role="alert" className="text-sm text-red-800">We couldn’t load the offboarding checklist.</p>
        <button type="button" onClick={() => void template.refetch()} className="mt-2 text-sm font-medium text-red-900 underline">Try again</button>
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-4 sm:p-6">
      <div className="flex flex-col gap-1 border-b border-gray-100 pb-4">
        <h2 className="text-lg font-semibold text-sr-text-blue">Offboarding checklist</h2>
        <p className="text-sm text-gray-600">
          These tasks are copied when People Operations starts offboarding. Existing employee checklists keep their original tasks.
        </p>
      </div>

      <div className="mt-4 space-y-4">
        {items.map((task, index) => (
          <fieldset key={`${index}-${task.title}`} className="grid gap-3 rounded-lg border border-gray-200 p-3 sm:grid-cols-[minmax(0,1fr)_12rem_auto] sm:p-4">
            <legend className="sr-only">Checklist task {index + 1}</legend>
            <div className="grid min-w-0 gap-3 sm:col-span-2">
              <label className="text-sm font-medium text-gray-700">
                Task name
                <input
                  required
                  maxLength={200}
                  value={task.title}
                  onChange={(event) => updateTask(index, { title: event.target.value })}
                  className="mt-1 h-10 w-full rounded-lg border border-gray-200 px-3 font-normal"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Instructions (optional)
                <textarea
                  maxLength={4000}
                  rows={2}
                  value={task.description ?? ""}
                  onChange={(event) => updateTask(index, { description: event.target.value })}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-normal"
                />
              </label>
            </div>
            <label className="text-sm font-medium text-gray-700">
              Due before last day
              <div className="mt-1 flex h-10 items-center gap-2 rounded-lg border border-gray-200 px-3">
                <input
                  type="number"
                  min={0}
                  max={365}
                  value={task.due_days_before_last_working_day}
                  onChange={(event) => updateTask(index, {
                    due_days_before_last_working_day: Number(event.target.value),
                  })}
                  className="w-16 border-0 p-0 text-sm font-normal outline-none"
                  aria-label={`Days before last working day for task ${index + 1}`}
                />
                <span className="text-xs font-normal text-gray-500">days</span>
              </div>
              <span className="mt-1 block text-xs font-normal text-gray-500">0 means due on the last working day.</span>
            </label>
            <button
              type="button"
              onClick={() => {
                setDraft(items.filter((_, taskIndex) => taskIndex !== index));
                setSaved(false);
                setError(null);
              }}
              disabled={items.length <= 1}
              className="h-10 self-start rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 sm:mt-6"
              aria-label={`Remove task ${index + 1}`}
            >
              Remove
            </button>
          </fieldset>
        ))}
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-red-800">{error}</p>}
      {saved && <p role="status" className="mt-4 text-sm text-emerald-800">Offboarding checklist saved for future offboarding plans.</p>}

      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={() => {
            setDraft([...items, {
              title: "",
              description: "",
              due_days_before_last_working_day: 0,
            }]);
            setSaved(false);
            setError(null);
          }}
          disabled={items.length >= 50}
          className="h-10 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Add task
        </button>
        <button
          type="button"
          onClick={save}
          disabled={saveTemplate.isPending || items.some((task) => !task.title.trim())}
          className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saveTemplate.isPending ? "Saving…" : "Save checklist"}
        </button>
      </div>
    </section>
  );
}
