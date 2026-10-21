"use client";

import { useMemo, useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import {
  useCancelEmployeeOffboarding,
  useApplicationEmployeeRecord,
  useCreateApplicationEmployeeRecord,
  useEmployeeOffboardingChecklist,
  useLinkEmployeeAccount,
  useStartEmployeeOffboarding,
  useUpdateEmployeeOffboardingTask,
  useUpdateEmployeeRecord,
} from "@/lib/api/hooks/employee-records";
import { useCurrentIdentity } from "@/lib/api/hooks/auth";
import { useTeamMembers, useWorkspaceMembers } from "@/lib/api/hooks/team";
import type {
  EmployeeOffboardingReason,
  EmployeeOffboardingTaskResponse,
  EmployeeOffboardingTaskStatus,
  EmployeeRecordResponse,
  EmployeeStatus,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";

const statusLabels: Record<EmployeeStatus, string> = {
  preboarding: "Preboarding",
  active: "Active",
  offboarding: "Offboarding",
  inactive: "Inactive",
};

const offboardingReasonLabels: Record<EmployeeOffboardingReason, string> = {
  resignation: "Resignation",
  retirement: "Retirement",
  redundancy: "Redundancy",
  contract_end: "End of contract",
  termination: "Termination",
  other: "Other",
};

const offboardingTaskStatusLabels: Record<EmployeeOffboardingTaskStatus, string> = {
  pending: "Not started",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
};

function EmployeeOffboardingTaskEditor({
  employeeId,
  employee,
  task,
  canManage,
}: {
  employeeId: string;
  employee: EmployeeRecordResponse;
  task: EmployeeOffboardingTaskResponse;
  canManage: boolean;
}) {
  const members = useTeamMembers();
  const updateTask = useUpdateEmployeeOffboardingTask();
  const [assigneeId, setAssigneeId] = useState(task.assigned_to_user_id ?? "");
  const [dueDate, setDueDate] = useState(task.due_date);
  const [taskStatus, setTaskStatus] = useState<EmployeeOffboardingTaskStatus>(task.status);
  const [completionNotes, setCompletionNotes] = useState(task.completion_notes ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    updateTask.mutate({
      taskId: task.id,
      employeeId,
      request: {
        expected_version: task.version,
        assigned_to_user_id: assigneeId || null,
        due_date: dueDate,
        status: taskStatus,
        completion_notes: completionNotes.trim() || null,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => setMessage("Checklist task saved."),
      onError: (cause) => setError(cause instanceof ApiError
        ? cause.detail
        : "This checklist task could not be saved. Refresh and try again."),
    });
  }

  return (
    <article className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h4 className="font-semibold text-gray-900">{task.position}. {task.title}</h4>
          {task.description && <p className="mt-1 text-sm text-gray-600">{task.description}</p>}
        </div>
        <span className="w-fit rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">
          {offboardingTaskStatusLabels[task.status]}
        </span>
      </div>

      <form onSubmit={save} className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium text-gray-700">
          Task owner
          <select
            value={assigneeId}
            onChange={(event) => setAssigneeId(event.target.value)}
            disabled={!canManage || members.isLoading || members.isError}
            className="mt-1 h-10 w-full rounded-lg border border-gray-200 bg-white px-3 font-normal disabled:bg-gray-50"
          >
            <option value="">Unassigned</option>
            {members.data?.items.map((member) => (
              <option key={member.id} value={member.id}>{member.display_name}</option>
            ))}
          </select>
          {members.isError && canManage && <span className="mt-1 block text-xs text-red-700">Workspace members could not be loaded.</span>}
        </label>
        <label className="text-sm font-medium text-gray-700">
          Due date
          <input
            type="date"
            required
            max={employee.last_working_day ?? undefined}
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
            disabled={!canManage}
            className="mt-1 h-10 w-full rounded-lg border border-gray-200 px-3 font-normal disabled:bg-gray-50"
          />
        </label>
        <label className="text-sm font-medium text-gray-700">
          Status
          <select
            value={taskStatus}
            onChange={(event) => setTaskStatus(event.target.value as EmployeeOffboardingTaskStatus)}
            disabled={!canManage}
            className="mt-1 h-10 w-full rounded-lg border border-gray-200 bg-white px-3 font-normal disabled:bg-gray-50"
          >
            {Object.entries(offboardingTaskStatusLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium text-gray-700 sm:col-span-2">
          Completion or handover notes
          <textarea
            rows={2}
            maxLength={4000}
            value={completionNotes}
            onChange={(event) => setCompletionNotes(event.target.value)}
            disabled={!canManage}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-normal disabled:bg-gray-50"
            placeholder="Optional notes for the handover record"
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-800 sm:col-span-2">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-800 sm:col-span-2">{message}</p>}
        {canManage && (
          <button
            type="submit"
            disabled={updateTask.isPending}
            className="h-10 w-fit rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2"
          >
            {updateTask.isPending ? "Saving…" : "Save task"}
          </button>
        )}
      </form>
    </article>
  );
}

function EmployeeOffboardingChecklist({
  employee,
  canManage,
}: {
  employee: EmployeeRecordResponse;
  canManage: boolean;
}) {
  const checklist = useEmployeeOffboardingChecklist(employee.id, canManage);

  if (!canManage) {
    return (
      <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <h4 className="text-sm font-semibold text-gray-900">Offboarding checklist</h4>
        <p className="mt-1 text-sm text-gray-600">Checklist details are available to workspace admins and People Operations.</p>
      </div>
    );
  }
  if (checklist.isLoading) {
    return <p className="mt-4 text-sm text-gray-600">Loading offboarding checklist…</p>;
  }
  if (checklist.isError) {
    return (
      <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
        <p role="alert" className="text-sm text-red-800">We couldn’t load the offboarding checklist.</p>
        <button type="button" onClick={() => void checklist.refetch()} className="mt-2 text-sm font-medium text-red-900 underline">Try again</button>
      </div>
    );
  }

  const items = checklist.data?.items ?? [];
  const total = checklist.data?.total_count ?? 0;
  const completed = checklist.data?.completed_count ?? 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold text-gray-900">Offboarding checklist</h4>
          <p className="mt-1 text-sm text-gray-600">Assign owners, update due dates, and record completion or handover notes.</p>
        </div>
        <span className="text-sm font-medium text-gray-700" aria-live="polite">{completed} of {total} tasks complete</span>
      </div>
      {total > 0 && (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100" role="progressbar" aria-label="Offboarding checklist progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
          <div className="h-full rounded-full bg-sr-green transition-all" style={{ width: `${percent}%` }} />
        </div>
      )}
      {items.length === 0 ? (
        <p className="mt-4 rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
          This offboarding plan has no checklist tasks. New plans use the template in Settings → Offboarding, or MindHire’s starter checklist if no template has been saved.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {items.map((task) => (
            <EmployeeOffboardingTaskEditor
              key={`${task.id}-${task.version}`}
              employeeId={employee.id}
              employee={employee}
              task={task}
              canManage={canManage}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EmployeeRecordForm({
  applicationId,
  employee,
  onSaved,
}: {
  applicationId: string;
  employee: EmployeeRecordResponse | null;
  onSaved: () => void;
}) {
  const members = useTeamMembers();
  const create = useCreateApplicationEmployeeRecord();
  const update = useUpdateEmployeeRecord();
  const [employeeNumber, setEmployeeNumber] = useState(employee?.employee_number ?? "");
  const [workEmail, setWorkEmail] = useState(employee?.work_email ?? "");
  const [startDate, setStartDate] = useState(employee?.start_date ?? "");
  const [jobTitle, setJobTitle] = useState(employee?.job_title ?? "");
  const [department, setDepartment] = useState(employee?.department ?? "");
  const [location, setLocation] = useState(employee?.location ?? "");
  const [managerId, setManagerId] = useState(employee?.manager_user_id ?? "");
  const [status, setStatus] = useState<EmployeeStatus>(employee?.status ?? "preboarding");
  const [error, setError] = useState<string | null>(null);
  const saving = create.isPending || update.isPending;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!employee) {
      create.mutate({
        applicationId,
        request: {
          employee_number: employeeNumber.trim() || null,
          work_email: workEmail.trim() || null,
          start_date: startDate || null,
          manager_user_id: managerId || null,
        },
        idempotencyKey: crypto.randomUUID(),
      }, {
        onSuccess: onSaved,
        onError: () => setError("The employee record could not be created. Refresh and try again."),
      });
      return;
    }

    const request: UpdateEmployeeRecordRequest = {
      expected_version: employee.version,
      employee_number: employeeNumber.trim() || null,
      work_email: workEmail.trim() || null,
      start_date: startDate || null,
      job_title: jobTitle.trim(),
      department: department.trim() || null,
      location: location.trim() || null,
      manager_user_id: managerId || null,
    };
    if (employee.status === "preboarding" || employee.status === "inactive") {
      request.status = status;
    }
    update.mutate({
      employeeId: employee.id,
      applicationId,
      request,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: onSaved,
      onError: () => setError("The employee record changed or could not be saved. Refresh and try again."),
    });
  }

  return (
    <form onSubmit={submit} className="mt-4 grid gap-4 sm:grid-cols-2">
      {employee && (
        <div className="sm:col-span-2">
          <p className="text-sm font-medium text-gray-900">{statusLabels[employee.status]}</p>
          <p className="mt-1 text-xs text-gray-500">Employee record is stored in MindHire. Candidate identity remains linked to the original application.</p>
        </div>
      )}
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Employee number</span>
        <input value={employeeNumber} onChange={(event) => setEmployeeNumber(event.target.value)} maxLength={50} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" placeholder="Optional" />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Work email</span>
        <input type="email" value={workEmail} onChange={(event) => setWorkEmail(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" placeholder="name@company.com" />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Start date</span>
        <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Manager</span>
        <select value={managerId} onChange={(event) => setManagerId(event.target.value)} disabled={members.isLoading || members.isError} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
          <option value="">Not assigned</option>
          {members.data?.items.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}
        </select>
        {members.isError && <span className="mt-1 block text-xs text-red-700">Workspace members could not be loaded.</span>}
      </label>
      {employee && (
        <>
          <label>
            <span className="mb-1 block text-sm font-medium text-gray-700">Job title</span>
            <input required value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} maxLength={200} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
          </label>
          <label>
            <span className="mb-1 block text-sm font-medium text-gray-700">Department</span>
            <input value={department} onChange={(event) => setDepartment(event.target.value)} maxLength={200} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
          </label>
          <label>
            <span className="mb-1 block text-sm font-medium text-gray-700">Work location</span>
            <input value={location} onChange={(event) => setLocation(event.target.value)} maxLength={200} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
          </label>
          {(employee.status === "preboarding" || employee.status === "inactive") && (
            <label>
              <span className="mb-1 block text-sm font-medium text-gray-700">Employment status</span>
              <select value={status} onChange={(event) => setStatus(event.target.value as EmployeeStatus)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                <option value={employee.status}>{statusLabels[employee.status]}</option>
                {(employee.status === "preboarding" ? ["active", "inactive"] : ["active"]).map((nextStatus) => <option key={nextStatus} value={nextStatus}>{statusLabels[nextStatus as EmployeeStatus]}</option>)}
              </select>
            </label>
          )}
        </>
      )}
      {error && <p role="alert" className="text-sm text-red-800 sm:col-span-2">{error}</p>}
      <button type="submit" disabled={saving || (employee !== null && !jobTitle.trim())} className="h-10 w-fit rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2">
        {saving ? "Saving…" : employee ? "Save employee details" : "Create employee record"}
      </button>
    </form>
  );
}

function EmployeeOffboardingSection({
  applicationId,
  employee,
  canManage,
}: {
  applicationId: string;
  employee: EmployeeRecordResponse;
  canManage: boolean;
}) {
  const startOffboarding = useStartEmployeeOffboarding();
  const cancelOffboarding = useCancelEmployeeOffboarding();
  const [lastWorkingDay, setLastWorkingDay] = useState("");
  const [reason, setReason] = useState<EmployeeOffboardingReason | "">("");
  const [confirmation, setConfirmation] = useState<"start" | "cancel" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const saving = startOffboarding.isPending || cancelOffboarding.isPending;

  function showError(cause: unknown) {
    setError(cause instanceof ApiError
      ? cause.detail
      : "The offboarding update could not be saved. Refresh and try again.");
  }

  function confirmStart() {
    if (!lastWorkingDay || !reason) {
      setError("Choose a last working day and a reason before continuing.");
      return;
    }
    setError(null);
    startOffboarding.mutate({
      employeeId: employee.id,
      applicationId,
      request: {
        expected_version: employee.version,
        last_working_day: lastWorkingDay,
        reason,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setConfirmation(null);
        setMessage("Offboarding has been recorded. The employee record and onboarding history remain available.");
      },
      onError: showError,
    });
  }

  function confirmCancel() {
    setError(null);
    cancelOffboarding.mutate({
      employeeId: employee.id,
      applicationId,
      request: { expected_version: employee.version },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setConfirmation(null);
        setLastWorkingDay("");
        setReason("");
        setMessage("Planned offboarding was cancelled. The employee is active again; the cancellation remains in the audit history.");
      },
      onError: showError,
    });
  }

  return (
    <section aria-labelledby="employee-offboarding-heading" className="mt-5 border-t border-gray-200 pt-5">
      <h3 id="employee-offboarding-heading" className="text-sm font-semibold text-gray-900">Offboarding</h3>
      <p className="mt-1 text-sm text-gray-600">
        Record a planned departure while keeping the employee record and historical onboarding information.
      </p>
      {message && <p role="status" className="mt-3 text-sm text-emerald-800">{message}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}

      {employee.status === "active" ? (
        canManage ? (
          <form
            className="mt-4 grid gap-3 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              setConfirmation("start");
            }}
          >
            <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
              Last working day
              <input
                type="date"
                required
                min={employee.start_date ?? undefined}
                value={lastWorkingDay}
                onChange={(event) => setLastWorkingDay(event.target.value)}
                className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
              Reason
              <select
                required
                value={reason}
                onChange={(event) => setReason(event.target.value as EmployeeOffboardingReason | "")}
                className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal"
              >
                <option value="">Choose a reason</option>
                {Object.entries(offboardingReasonLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={saving}
              className="h-10 w-fit rounded-lg border border-sr-text-blue px-4 text-sm font-semibold text-sr-text-blue hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2"
            >
              Review offboarding
            </button>
          </form>
        ) : (
          <p className="mt-3 text-sm text-gray-600">Only workspace admins and People Operations can start or cancel offboarding.</p>
        )
      ) : employee.status === "offboarding" ? (
        <div className="mt-4 rounded-lg bg-amber-50 p-4">
          {canManage ? (
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-gray-600">Last working day</dt>
                <dd className="mt-0.5 font-medium text-gray-900">{employee.last_working_day ?? "Not recorded"}</dd>
              </div>
              <div>
                <dt className="text-gray-600">Reason</dt>
                <dd className="mt-0.5 font-medium text-gray-900">
                  {employee.offboarding_reason ? offboardingReasonLabels[employee.offboarding_reason] : "Not recorded"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-amber-950">
              The planned last working day and departure reason are restricted to workspace admins and People Operations.
            </p>
          )}
          <p className="mt-3 text-sm text-amber-950">
            This records the planned departure only. It does not disable the employee’s workspace login or delete their record and onboarding history.
          </p>
          {canManage ? (
            <button
              type="button"
              onClick={() => { setError(null); setConfirmation("cancel"); }}
              disabled={saving}
              className="mt-3 h-9 rounded-lg border border-amber-900/30 px-3 text-sm font-semibold text-amber-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel planned offboarding
            </button>
          ) : (
            <p className="mt-3 text-sm text-gray-600">Only workspace admins and People Operations can cancel offboarding.</p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-600">
          Offboarding can be started after this employee record is active.
        </p>
      )}

      {employee.status === "offboarding" && (
        <EmployeeOffboardingChecklist employee={employee} canManage={canManage} />
      )}

      {confirmation && (
        <div
          role="group"
          aria-labelledby="employee-offboarding-confirmation-title"
          aria-describedby="employee-offboarding-confirmation-description"
          className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4"
        >
          <h4 id="employee-offboarding-confirmation-title" className="text-sm font-semibold text-gray-900">
            {confirmation === "start" ? "Confirm planned offboarding" : "Cancel planned offboarding?"}
          </h4>
          <p id="employee-offboarding-confirmation-description" className="mt-1 text-sm text-gray-700">
            {confirmation === "start"
              ? `Record ${lastWorkingDay} as the last working day and ${reason ? offboardingReasonLabels[reason] : "the selected reason"} as the reason. MindHire will create a checklist from Settings → Offboarding, or use its starter checklist if you have not saved one. The employee’s workspace login stays active.`
              : "This restores the employee status to Active and clears the current planned departure details. The cancellation is retained in the audit history."}
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={confirmation === "start" ? confirmStart : confirmCancel}
              disabled={saving}
              className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving…" : confirmation === "start" ? "Confirm offboarding" : "Confirm cancellation"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmation(null)}
              disabled={saving}
              className="h-10 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Go back
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function EmployeeAccountLinkSection({
  applicationId,
  employee,
  candidateEmail,
}: {
  applicationId: string;
  employee: EmployeeRecordResponse;
  candidateEmail: string | null;
}) {
  const members = useWorkspaceMembers();
  const linkAccount = useLinkEmployeeAccount();
  const [selectedUserId, setSelectedUserId] = useState(employee.user_id ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eligibleEmails = useMemo(() => new Set(
    [candidateEmail, employee.work_email]
      .map((email) => email?.trim().toLowerCase())
      .filter((email): email is string => Boolean(email)),
  ), [candidateEmail, employee.work_email]);

  const linkableMembers = useMemo(() => {
    const workspaceMembers = members.data?.items ?? [];
    return workspaceMembers.filter((member) =>
      eligibleEmails.has(member.email.trim().toLowerCase()) ||
      member.id === employee.user_id,
    );
  }, [eligibleEmails, employee.user_id, members.data?.items]);

  const currentMember = members.data?.items.find(
    (member) => member.id === employee.user_id,
  );
  function saveLink() {
    setError(null);
    setMessage(null);
    linkAccount.mutate({
      employeeId: employee.id,
      applicationId,
      request: {
        user_id: selectedUserId || null,
        expected_version: employee.version,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: (linkedAccount) => {
        setSelectedUserId(linkedAccount.user_id ?? "");
        setMessage(linkedAccount.user_id
          ? "Employee portal account linked."
          : "Employee portal account unlinked.");
      },
      onError: (cause) => setError(
        cause instanceof ApiError
          ? cause.detail
          : "The account link could not be saved. Refresh and try again.",
      ),
    });
  }

  return (
    <div className="mt-5 border-t border-gray-200 pt-5">
      <h3 className="text-sm font-semibold text-gray-900">Employee portal access</h3>
      <p className="mt-1 text-sm text-gray-600">
        Link an existing workspace account whose email matches the candidate or work email. The employee can then view their own onboarding checklist.
      </p>
      {members.isLoading ? (
        <p role="status" className="mt-3 text-sm text-gray-600">Loading eligible workspace accounts…</p>
      ) : members.isError ? (
        <div className="mt-3">
          <p role="alert" className="text-sm text-red-800">Workspace accounts could not be loaded.</p>
          <button type="button" onClick={() => void members.refetch()} className="mt-1 text-sm font-medium text-sr-text-blue underline">Try again</button>
        </div>
      ) : (
        <>
          <p className="mt-3 text-sm text-gray-700">
            {employee.user_id
              ? `Linked to ${currentMember?.display_name ?? "a workspace account"}${currentMember ? ` (${currentMember.email})` : ""}.`
              : "No workspace account is linked."}
          </p>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm font-medium text-gray-700">
              Workspace account
              <select
                value={selectedUserId}
                onChange={(event) => {
                  setSelectedUserId(event.target.value);
                  setError(null);
                  setMessage(null);
                }}
                disabled={linkAccount.isPending || linkableMembers.length === 0}
                className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 disabled:bg-gray-50"
              >
                <option value="">No account linked</option>
                {linkableMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.display_name} · {member.email}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={saveLink}
              disabled={linkAccount.isPending || selectedUserId === (employee.user_id ?? "") || (!selectedUserId && !employee.user_id)}
              className="h-10 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {linkAccount.isPending
                ? "Saving…"
                : selectedUserId
                  ? "Link account"
                  : "Unlink account"}
            </button>
          </div>
          {linkableMembers.length === 0 && !employee.user_id && (
            <p className="mt-2 text-sm text-amber-800">
              {eligibleEmails.size === 0
                ? "Add the candidate or work email to the employee record to find a matching workspace account."
                : "No existing workspace account matches the candidate or work email. The account must exist in this workspace and use one of those email addresses."}
            </p>
          )}
          {message && <p role="status" className="mt-2 text-sm text-emerald-800">{message}</p>}
          {error && <p role="alert" className="mt-2 text-sm text-red-800">{error}</p>}
        </>
      )}
    </div>
  );
}

export function ApplicationEmployeeRecordSection({
  applicationId,
  applicationStatus,
  candidateEmail,
}: {
  applicationId: string;
  applicationStatus: string;
  candidateEmail: string | null;
}) {
  const eligible = applicationStatus === "hired";
  const employeeQuery = useApplicationEmployeeRecord(applicationId, eligible);
  const identityQuery = useCurrentIdentity();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const canManagePortalAccess = identityQuery.data?.roles.some(
    (role) => role === "tenant_admin" || role === "people_operations",
  ) ?? false;
  if (!eligible) return null;

  return (
    <section aria-labelledby="employee-record-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <h2 id="employee-record-heading" className="text-base font-semibold text-sr-text-blue">Employee record</h2>
      <p className="mt-1 text-sm text-gray-600">Manage employment details in MindHire. Job details are prefilled from the requisition and can be updated here.</p>
      {employeeQuery.isLoading ? <p role="status" className="mt-4 text-sm text-gray-600">Loading employee record…</p> : employeeQuery.isError ? (
        <p role="alert" className="mt-4 text-sm text-red-800">We couldn’t load this employee record.</p>
      ) : (
        <>
          {statusMessage && <p role="status" className="mt-4 text-sm text-emerald-800">{statusMessage}</p>}
          <EmployeeRecordForm
            key={`${employeeQuery.data?.id ?? "new"}-${employeeQuery.data?.version ?? 0}`}
            applicationId={applicationId}
            employee={employeeQuery.data ?? null}
            onSaved={() => setStatusMessage("Employee details saved in MindHire.")}
          />
          {employeeQuery.data && (
            <EmployeeOffboardingSection
              applicationId={applicationId}
              employee={employeeQuery.data}
              canManage={canManagePortalAccess}
            />
          )}
          {canManagePortalAccess && employeeQuery.data && (
            <EmployeeAccountLinkSection
              applicationId={applicationId}
              employee={employeeQuery.data}
              candidateEmail={candidateEmail}
            />
          )}
        </>
      )}
    </section>
  );
}
