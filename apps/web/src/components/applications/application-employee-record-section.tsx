"use client";

import { useState, type FormEvent } from "react";
import {
  useApplicationEmployeeRecord,
  useCreateApplicationEmployeeRecord,
  useUpdateEmployeeRecord,
} from "@/lib/api/hooks/employee-records";
import { useTeamMembers } from "@/lib/api/hooks/team";
import type {
  EmployeeRecordResponse,
  EmployeeStatus,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";

const statusLabels: Record<EmployeeStatus, string> = {
  preboarding: "Preboarding",
  active: "Active",
  inactive: "Inactive",
};

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
      status,
    };
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
          <label>
            <span className="mb-1 block text-sm font-medium text-gray-700">Employment status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value as EmployeeStatus)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
              <option value={employee.status}>{statusLabels[employee.status]}</option>
              {(employee.status === "preboarding" ? ["active", "inactive"] : employee.status === "active" ? ["inactive"] : ["active"]).map((nextStatus) => <option key={nextStatus} value={nextStatus}>{statusLabels[nextStatus as EmployeeStatus]}</option>)}
            </select>
          </label>
        </>
      )}
      {error && <p role="alert" className="text-sm text-red-800 sm:col-span-2">{error}</p>}
      <button type="submit" disabled={saving || (employee !== null && !jobTitle.trim())} className="h-10 w-fit rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2">
        {saving ? "Saving…" : employee ? "Save employee details" : "Create employee record"}
      </button>
    </form>
  );
}

export function ApplicationEmployeeRecordSection({
  applicationId,
  applicationStatus,
}: {
  applicationId: string;
  applicationStatus: string;
}) {
  const eligible = applicationStatus === "hired";
  const employeeQuery = useApplicationEmployeeRecord(applicationId, eligible);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
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
        </>
      )}
    </section>
  );
}
