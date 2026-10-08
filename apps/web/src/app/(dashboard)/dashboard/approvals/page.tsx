"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { useAssignedRequisitionApprovals } from "@/lib/api/hooks/approvals";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
    new Date(value),
  );
}

export default function ApprovalsInboxPage() {
  const { status } = useSession();
  const inboxQuery = useAssignedRequisitionApprovals();
  const approvals = inboxQuery.data?.items ?? [];
  const isLoading = status === "loading" || inboxQuery.isLoading;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">
          Approvals
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Review requisitions assigned to you in the workspace approval process.
        </p>
      </header>

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading your approvals…
        </div>
      ) : status !== "authenticated" ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50 p-8">
          <h2 className="font-semibold text-amber-950">Sign in to view approvals</h2>
        </section>
      ) : inboxQuery.isError ? (
        <section className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p role="alert" className="text-sm text-red-800">
            We couldn’t load approvals assigned to you.
          </p>
          <Button className="mt-4" variant="outline" onClick={() => void inboxQuery.refetch()}>
            Try again
          </Button>
        </section>
      ) : approvals.length ? (
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 bg-white">
          {approvals.map((approval) => (
            <li key={approval.approval_id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h2 className="truncate font-semibold text-sr-text-blue">{approval.title}</h2>
                <p className="mt-1 text-sm text-gray-600">
                  {[approval.department, approval.location, `${approval.headcount} ${approval.headcount === 1 ? "opening" : "openings"}`]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  Submitted {formatDate(approval.submitted_at)} · Step {approval.assigned_step}
                  {approval.is_current_approver ? " · Your turn" : ` · Current step ${approval.current_step}`}
                </p>
              </div>
              <Button asChild variant={approval.is_current_approver ? "default" : "outline"}>
                <Link href={`/dashboard/approvals/${approval.approval_id}`}>
                  {approval.is_current_approver ? "Review requisition" : "View status"}
                </Link>
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <section className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <h2 className="font-semibold text-sr-text-blue">No requisitions assigned to you</h2>
          <p className="mt-1 text-sm text-gray-500">
            Requisitions requiring your approval will appear here.
          </p>
        </section>
      )}
    </div>
  );
}
