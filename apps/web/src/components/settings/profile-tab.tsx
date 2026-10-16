"use client";

import { useSession } from "next-auth/react";
import { Mail, ShieldCheck, UserRound } from "lucide-react";
import { getUserDisplayName } from "@/lib/user-display-name";
import type { Role } from "@/types/api/auth";

const roleLabels: Record<Role, string> = {
  tenant_admin: "Workspace admin",
  recruiter: "Recruiter",
  hiring_manager: "Hiring manager",
  interviewer: "Interviewer",
  people_operations: "People operations",
  analyst: "Analyst",
};

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase() ?? "")
    .join("");
}

export function ProfileTab() {
  const { data: session, status } = useSession();
  const email = session?.user?.email?.trim() || "Email unavailable";
  const name = getUserDisplayName(session?.user?.name, session?.user?.email) ?? "Name unavailable";
  const roles = session?.roles ?? [];

  if (status === "loading") {
    return (
      <section aria-label="Loading profile" className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <p className="text-sm text-gray-500">Loading your profile…</p>
      </section>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="flex flex-col gap-4 border-b border-gray-100 p-6 sm:flex-row sm:items-center sm:gap-5">
        <div
          aria-hidden="true"
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-sr-mint text-2xl font-bold text-sr-text-blue"
        >
          {name === "Name unavailable" ? <UserRound className="h-7 w-7" /> : getInitials(name)}
        </div>
        <div className="min-w-0">
          <h2 className="wrap-break-word text-xl font-bold text-sr-text-blue">{name}</h2>
          <p className="mt-1 break-all text-sm text-gray-500">{email}</p>
        </div>
      </header>

      <div className="grid gap-6 p-6 sm:p-8 md:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">Account name</h3>
          <p className="mt-2 wrap-break-word text-sm text-gray-700">{name}</p>
        </div>

        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">Email address</h3>
          <p className="mt-2 flex min-w-0 items-center gap-2 break-all text-sm text-gray-700">
            <Mail aria-hidden="true" className="h-4 w-4 shrink-0 text-gray-400" />
            {email}
          </p>
        </div>

        <div className="md:col-span-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <ShieldCheck aria-hidden="true" className="h-4 w-4 text-gray-400" />
            Workspace access
          </h3>
          {roles.length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-2">
              {roles.map((role) => (
                <li key={role} className="rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700">
                  {roleLabels[role]}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-gray-500">No workspace roles are available for this account.</p>
          )}
        </div>
      </div>

      <footer className="border-t border-gray-100 bg-gray-50 px-6 py-4 sm:px-8">
        <p className="text-sm text-gray-600">
          Your name and email come from your sign-in account and are read-only in this workspace.
        </p>
      </footer>
    </section>
  );
}
