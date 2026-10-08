"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { getUserFirstName } from "@/lib/user-display-name";

export default function DashboardPage() {
  const { data: session } = useSession();
  const name = getUserFirstName(session?.user?.name, session?.user?.email);

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8">
      <header>
        <p className="text-sm font-medium text-gray-500">Recruiter workspace</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
          {name ? `Welcome, ${name}` : "Welcome to MindHire"}
        </h1>
        <p className="mt-2 text-sm text-gray-600">
          Manage hiring requests and move approved roles into recruiting.
        </p>
      </header>

      <section aria-labelledby="get-started-heading">
        <h2 id="get-started-heading" className="text-lg font-semibold text-sr-text-blue">
          Hiring workspace
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Link
            href="/dashboard/requisitions"
            className="group rounded-xl border border-gray-200 bg-white p-6 transition-colors hover:border-sr-green"
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Plan</span>
            <h3 className="mt-2 text-lg font-semibold text-sr-text-blue group-hover:text-sr-green">
              Requisitions
            </h3>
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Create hiring requests and track their approval status.
            </p>
            <span className="mt-4 inline-block text-sm font-semibold text-sr-text-blue">View requisitions →</span>
          </Link>

          <Link
            href="/dashboard/jobs"
            className="group rounded-xl border border-gray-200 bg-white p-6 transition-colors hover:border-sr-green"
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Recruit</span>
            <h3 className="mt-2 text-lg font-semibold text-sr-text-blue group-hover:text-sr-green">
              Job postings
            </h3>
            <p className="mt-2 text-sm leading-6 text-gray-600">
              Review draft, published, and expired job postings for your workspace.
            </p>
            <span className="mt-4 inline-block text-sm font-semibold text-sr-text-blue">View job postings →</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
