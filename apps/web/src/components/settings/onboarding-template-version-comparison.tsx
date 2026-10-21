import type {
  OnboardingTemplateResponse,
  OnboardingTemplateTaskResponse,
} from "@/types/api/onboarding";

interface OnboardingTemplateVersionComparisonProps {
  current: OnboardingTemplateResponse | null;
  draft: OnboardingTemplateResponse;
}

interface TaskFieldChange {
  label: string;
  before: string;
  after: string;
}

interface MatchedTaskChange {
  task: OnboardingTemplateTaskResponse;
  changes: TaskFieldChange[];
}

function taskIdentity(title: string): string {
  return title.trim().toLowerCase();
}

function sortedTasks(template: OnboardingTemplateResponse): OnboardingTemplateTaskResponse[] {
  return [...template.tasks].sort((left, right) => left.position - right.position);
}

function displayValue(value: string | null | undefined): string {
  return value?.trim() || "None";
}

function displayRole(role: string | null): string {
  return role
    ? role.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ")
    : "Unassigned";
}

function displayPrerequisites(
  positions: number[],
  tasks: OnboardingTemplateTaskResponse[],
): string {
  if (positions.length === 0) return "None";
  return positions
    .map((position) => tasks.find((task) => task.position === position)?.title)
    .filter((title): title is string => Boolean(title))
    .join(", ") || "None";
}

function getTaskChanges(
  before: OnboardingTemplateTaskResponse,
  after: OnboardingTemplateTaskResponse,
  beforeTasks: OnboardingTemplateTaskResponse[],
  afterTasks: OnboardingTemplateTaskResponse[],
): TaskFieldChange[] {
  const changes: TaskFieldChange[] = [];
  const addChange = (label: string, oldValue: string, newValue: string) => {
    if (oldValue !== newValue) changes.push({ label, before: oldValue, after: newValue });
  };

  addChange("Description", displayValue(before.description), displayValue(after.description));
  addChange(
    "Due date",
    before.due_offset_days === null ? "No due date" : `${before.due_offset_days} days after start`,
    after.due_offset_days === null ? "No due date" : `${after.due_offset_days} days after start`,
  );
  addChange(
    "Responsible party",
    before.responsible_party === "employee" ? "Employee" : "Workspace team",
    after.responsible_party === "employee" ? "Employee" : "Workspace team",
  );
  addChange(
    "Default assignee",
    displayRole(before.default_assignee_role),
    displayRole(after.default_assignee_role),
  );
  addChange(
    "Document upload",
    before.requires_document_upload ? "Required" : "Not required",
    after.requires_document_upload ? "Required" : "Not required",
  );
  addChange(
    "People Operations review",
    before.requires_document_review ? "Required" : "Not required",
    after.requires_document_review ? "Required" : "Not required",
  );
  addChange(
    "Prerequisites",
    displayPrerequisites(before.prerequisite_task_positions, beforeTasks),
    displayPrerequisites(after.prerequisite_task_positions, afterTasks),
  );

  return changes;
}

function taskSummary(task: OnboardingTemplateTaskResponse): string {
  return [
    task.responsible_party === "employee" ? "Employee task" : "Workspace team task",
    task.due_offset_days === null ? "No due date" : `Due ${task.due_offset_days} days after onboarding starts`,
    task.requires_document_upload ? "File upload required" : null,
    task.requires_document_review ? "People Operations review required" : null,
  ].filter((detail): detail is string => detail !== null).join(" · ");
}

export function OnboardingTemplateVersionComparison({
  current,
  draft,
}: OnboardingTemplateVersionComparisonProps) {
  if (!current) {
    return (
      <section className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4" aria-label="Draft version comparison">
        <h3 className="text-sm font-semibold text-blue-950">First version</h3>
        <p className="mt-1 text-sm text-blue-900">
          There is no published version to compare. Review the employee checklist below before publishing this template.
        </p>
      </section>
    );
  }

  const beforeTasks = sortedTasks(current);
  const afterTasks = sortedTasks(draft);
  const unmatchedBefore = new Map<string, OnboardingTemplateTaskResponse[]>();
  beforeTasks.forEach((task) => {
    const identity = taskIdentity(task.title);
    unmatchedBefore.set(identity, [...(unmatchedBefore.get(identity) ?? []), task]);
  });

  const added: OnboardingTemplateTaskResponse[] = [];
  const updated: MatchedTaskChange[] = [];
  const matchedBeforePositions: number[] = [];
  afterTasks.forEach((task) => {
    const matches = unmatchedBefore.get(taskIdentity(task.title));
    const previous = matches?.shift();
    if (!previous) {
      added.push(task);
      return;
    }
    matchedBeforePositions.push(beforeTasks.indexOf(previous));
    const changes = getTaskChanges(previous, task, beforeTasks, afterTasks);
    if (changes.length > 0) updated.push({ task, changes });
  });

  const removed = [...unmatchedBefore.values()].flat();
  const orderChanged = matchedBeforePositions.some(
    (position, index) => index > 0 && position < matchedBeforePositions[index - 1],
  );
  const hasChanges = added.length > 0 || removed.length > 0 || updated.length > 0 || orderChanged;

  return (
    <section className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50 p-4" aria-label="Draft version comparison">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-indigo-950">
            Compared with published version {current.version}
          </h3>
          <p className="mt-1 text-sm text-indigo-900">
            Review these checklist changes before publishing version {draft.version} for future hires.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-medium" role="group" aria-label="Change summary">
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-900">{added.length} added</span>
          <span className="rounded-full bg-red-100 px-2.5 py-1 text-red-900">{removed.length} removed</span>
          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-950">{updated.length} changed</span>
          {orderChanged && <span className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-950">Order changed</span>}
        </div>
      </div>

      {!hasChanges ? (
        <p className="mt-4 rounded-md bg-white/80 p-3 text-sm text-indigo-950">
          No checklist changes. Publishing will create a new version with the same tasks.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {added.map((task) => (
            <li key={`added-${task.id}`} className="rounded-md border border-emerald-200 bg-white p-3">
              <p className="text-sm font-semibold text-emerald-900">Added: {task.title}</p>
              <p className="mt-1 text-xs text-gray-700">{taskSummary(task)}</p>
              {task.description && <p className="mt-1 text-xs text-gray-600">{task.description}</p>}
            </li>
          ))}
          {removed.map((task) => (
            <li key={`removed-${task.id}`} className="rounded-md border border-red-200 bg-white p-3">
              <p className="text-sm font-semibold text-red-900">Removed: {task.title}</p>
              <p className="mt-1 text-xs text-gray-700">{taskSummary(task)}</p>
              {task.description && <p className="mt-1 text-xs text-gray-600">{task.description}</p>}
            </li>
          ))}
          {updated.map(({ task, changes }) => (
            <li key={`updated-${task.id}`} className="rounded-md border border-amber-200 bg-white p-3">
              <p className="text-sm font-semibold text-amber-950">Changed: {task.title}</p>
              <dl className="mt-2 space-y-1 text-xs">
                {changes.map((change) => (
                  <div key={change.label} className="grid gap-1 sm:grid-cols-[10rem_1fr]">
                    <dt className="font-medium text-gray-700">{change.label}</dt>
                    <dd className="break-words text-gray-600">
                      <span className="text-red-800">{change.before}</span>
                      <span className="mx-2 text-gray-400" aria-hidden="true">→</span>
                      <span className="text-emerald-800">{change.after}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
          {orderChanged && (
            <li className="rounded-md border border-amber-200 bg-white p-3 text-sm text-amber-950">
              The order of existing tasks has changed.
            </li>
          )}
        </ul>
      )}

      <p className="mt-3 text-xs text-indigo-900">
        Tasks are matched by title. A renamed task appears as a removal and an addition. Existing onboarding plans are not affected.
      </p>
    </section>
  );
}
