"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import {
  useEmployeeDirectory,
  useEmployeeDirectoryFilterOptions,
} from "@/lib/api/hooks/employee-records";
import type { EmployeeStatus } from "@/types/api/employee-records";

const PAGE_SIZE = 25;

const employeeStatuses: { value: EmployeeStatus; label: string }[] = [
  { value: "preboarding", label: "Preboarding" },
  { value: "active", label: "Active" },
  { value: "offboarding", label: "Offboarding" },
  { value: "inactive", label: "Inactive" },
];

function formatDate(value: string | null): string {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function statusStyle(status: EmployeeStatus): string {
  if (status === "active") return "bg-emerald-50 text-emerald-800";
  if (status === "inactive") return "bg-gray-100 text-gray-700";
  if (status === "offboarding") return "bg-orange-50 text-orange-900";
  return "bg-amber-50 text-amber-900";
}

function statusLabel(status: EmployeeStatus): string {
  return employeeStatuses.find((option) => option.value === status)?.label ?? status;
}

export default function EmployeesPage() {
  const { status: sessionStatus } = useSession();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<EmployeeStatus | "">("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [page, setPage] = useState(1);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
  }, []);

  const employeeQuery = useEmployeeDirectory({
    page,
    limit: PAGE_SIZE,
    query: query || undefined,
    status: status || undefined,
    department: department || undefined,
    location: location || undefined,
  });
  const optionsQuery = useEmployeeDirectoryFilterOptions();
  const employees = employeeQuery.data?.items ?? [];
  const total = employeeQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(query || status || department || location);
  const isLoading = sessionStatus === "loading" || employeeQuery.isLoading;
  const errorMessage = employeeQuery.error instanceof Error
    ? employeeQuery.error.message
    : "We couldn’t load employees from this workspace.";

  function updateSearch(value: string) {
    setSearchInput(value);
    setPage(1);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setQuery(value.trim()), 250);
  }

  function clearFilters() {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = null;
    setSearchInput("");
    setQuery("");
    setStatus("");
    setDepartment("");
    setLocation("");
    setPage(1);
  }

  return (
    <div className="mx-auto flex w-full max-w-375 flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Employees</h1>
        <p className="mt-1 text-sm text-gray-600">
          Browse employees hired through your workspace and manage their employment details.
        </p>
      </header>

      <section aria-label="Employee filters" className="grid min-w-0 gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-4">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Search employees
          <input
            type="search"
            value={searchInput}
            onChange={(event) => updateSearch(event.target.value)}
            placeholder="Name, role, number, work email"
            className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as EmployeeStatus | "");
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All statuses</option>
            {employeeStatuses.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Department
          <select
            value={department}
            onChange={(event) => {
              setDepartment(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All departments</option>
            {(optionsQuery.data?.departments ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-gray-600">
          Location
          <select
            value={location}
            onChange={(event) => {
              setLocation(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All locations</option>
            {(optionsQuery.data?.locations ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        {hasFilters && (
          <div className="sm:col-span-2 xl:col-span-4">
            <button type="button" onClick={clearFilters} className="text-sm font-medium text-sr-text-blue underline-offset-4 hover:underline">
              Clear filters
            </button>
          </div>
        )}
      </section>

      <section aria-label="Employee directory" className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <p role="status" className="p-10 text-center text-sm text-gray-600">Loading employees…</p>
        ) : sessionStatus !== "authenticated" ? (
          <p className="p-10 text-center text-sm text-gray-600">Sign in to view workspace employees.</p>
        ) : employeeQuery.isError ? (
          <div className="p-10 text-center">
            <p role="alert" className="text-sm text-red-800">{errorMessage}</p>
            <button type="button" onClick={() => void employeeQuery.refetch()} className="mt-3 text-sm font-medium text-sr-text-blue underline">Try again</button>
          </div>
        ) : employees.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <h2 className="text-base font-semibold text-sr-text-blue">
              {hasFilters ? "No employees match these filters" : "No employees yet"}
            </h2>
            <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600">
              {hasFilters
                ? "Try changing or clearing the search and filters."
                : "Employee records appear here when onboarding starts for a hired application."}
            </p>
            {hasFilters && <button type="button" onClick={clearFilters} className="mt-4 text-sm font-medium text-sr-text-blue underline">Clear filters</button>}
          </div>
        ) : (
          <>
            <div
              role="region"
              aria-label="Employee directory table"
              tabIndex={0}
              className="max-w-full overflow-x-auto overscroll-x-contain focus-visible:outline focus-visible:outline-2 focus-visible:outline-sr-green"
            >
              <p className="px-4 py-2 text-xs text-gray-500 sm:hidden">
                Swipe horizontally to see all employee details.
              </p>
              <table className="w-full min-w-[1220px] text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50 text-xs font-medium uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-5 py-3">Employee</th>
                    <th scope="col" className="px-5 py-3">Employee number</th>
                    <th scope="col" className="px-5 py-3">Job title</th>
                    <th scope="col" className="px-5 py-3">Department</th>
                    <th scope="col" className="px-5 py-3">Location</th>
                    <th scope="col" className="px-5 py-3">Start date</th>
                    <th scope="col" className="px-5 py-3">Last working day</th>
                    <th scope="col" className="px-5 py-3">Status</th>
                    <th scope="col" className="px-5 py-3"><span className="sr-only">Open application</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {employees.map((employee) => (
                    <tr key={employee.id} className="transition-colors hover:bg-gray-50">
                      <td className="px-5 py-4">
                        <Link href={`/dashboard/applications/${employee.application_id}`} className="font-medium text-sr-text-blue hover:underline">
                          {employee.employee_name}
                        </Link>
                        <p className="mt-0.5 text-xs text-gray-500">{employee.work_email || "Employee record"}</p>
                      </td>
                      <td className="px-5 py-4 text-gray-700">{employee.employee_number || "—"}</td>
                      <td className="px-5 py-4 text-gray-800">{employee.job_title}</td>
                      <td className="px-5 py-4 text-gray-700">{employee.department || "—"}</td>
                      <td className="px-5 py-4 text-gray-700">{employee.location || "—"}</td>
                      <td className="px-5 py-4 text-gray-700">{formatDate(employee.start_date)}</td>
                      <td className="px-5 py-4 text-gray-700">
                        {employee.status === "offboarding" && !employee.last_working_day
                          ? "Restricted"
                          : formatDate(employee.last_working_day)}
                      </td>
                      <td className="px-5 py-4">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle(employee.status)}`}>
                          {statusLabel(employee.status)}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Link href={`/dashboard/applications/${employee.application_id}`} className="text-sm font-medium text-sr-text-blue hover:underline">View</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <footer className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p aria-live="polite" className="text-sm text-gray-600">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} employees
              </p>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || employeeQuery.isFetching}
                  className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="min-w-20 text-center text-sm text-gray-600">Page {page} of {pageCount}</span>
                <button
                  type="button"
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  disabled={page >= pageCount || employeeQuery.isFetching}
                  className="h-9 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
