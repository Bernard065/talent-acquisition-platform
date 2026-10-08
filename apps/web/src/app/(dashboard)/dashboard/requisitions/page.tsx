"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  useRequisitions,
  useSubmitRequisitionForApproval,
} from "@/lib/api/hooks/requisitions";
import { useCurrentIdentity } from "@/lib/api/hooks/auth";
import type { RequisitionStatus } from "@/types/api/requisitions";

const statusStyle: Record<RequisitionStatus, string> = {
  draft: "bg-gray-100 text-gray-700",
  pending_approval: "bg-amber-50 text-amber-800",
  approved: "bg-blue-50 text-blue-800",
  open: "bg-green-50 text-green-800",
  on_hold: "bg-orange-50 text-orange-800",
  closed: "bg-gray-100 text-gray-600",
  cancelled: "bg-red-50 text-red-700",
};

function formatStatus(status: RequisitionStatus) {
  return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function RequisitionsPage() {
  const [actionError, setActionError] = useState<string | null>(null);
  const { status: sessionStatus } = useSession();
  const identityQuery = useCurrentIdentity();
  const isWorkspaceAdmin = identityQuery.data?.roles.includes("tenant_admin") ?? false;
  const requisitionsQuery = useRequisitions({ limit: 100 });
  const submitMutation = useSubmitRequisitionForApproval();
  const requisitions = requisitionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const isLoading = sessionStatus !== "authenticated" || requisitionsQuery.isLoading;
  const error = requisitionsQuery.isError
    ? "We couldn’t load requisitions from your workspace. Please try again."
    : null;

  async function submitForApproval(requisitionId: string) {
    setActionError(null);
    try {
      await submitMutation.mutateAsync({
        requisitionId,
        idempotencyKey: crypto.randomUUID(),
      });
    } catch (cause) {
      setActionError(
        cause instanceof Error
          ? cause.message
          : "We couldn’t submit this requisition for approval.",
      );
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Requisitions</h1>
          <p className="mt-1 text-sm text-gray-500">Plan and track hiring requests through approval.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {isWorkspaceAdmin && (
            <Button asChild variant="outline">
              <Link href="/dashboard/settings/approvals">Approval settings</Link>
            </Button>
          )}
          <Button asChild>
            <Link href="/dashboard/jobs/new">Create requisition</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-sm text-red-800">{error}</p>
          <Button className="mt-4" variant="outline" onClick={() => void requisitionsQuery.refetch()}>Try again</Button>
        </div>
      ) : isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading requisitions…
        </div>
      ) : requisitions.length ? (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          {actionError && (
            <p role="alert" className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-800">
              {actionError}
            </p>
          )}
          <div className="hidden grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_auto] gap-4 border-b border-gray-100 bg-gray-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid">
            <span>Role</span><span>Department</span><span>Openings</span><span>Status</span><span>Actions</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {requisitions.map((requisition) => (
              <li key={requisition.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_auto] md:items-center md:gap-4">
                <div className="min-w-0">
                  <h2 className="truncate font-semibold text-sr-text-blue">{requisition.title}</h2>
                  <p className="mt-1 truncate text-sm text-gray-500">
                    {[requisition.location, new Date(requisition.created_at).toLocaleDateString()]
                      .filter(Boolean).join(" · ")}
                  </p>
                </div>
                <div className="text-sm text-gray-700">{requisition.department ?? "—"}</div>
                <div className="text-sm text-gray-700">{requisition.headcount}</div>
                <div>
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle[requisition.status]}`}>
                    {formatStatus(requisition.status)}
                  </span>
                </div>
                <div>
                  {requisition.status === "draft" ? (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={submitMutation.isPending}
                      onClick={() => void submitForApproval(requisition.id)}
                    >
                      {submitMutation.isPending
                        && submitMutation.variables?.requisitionId === requisition.id
                        ? "Submitting…"
                        : "Submit for approval"}
                    </Button>
                  ) : requisition.status === "pending_approval" ? (
                    <span className="text-sm text-gray-500">Awaiting approval</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          {requisitionsQuery.hasNextPage && (
            <div className="flex justify-center border-t border-gray-100 p-4">
              <Button
                variant="outline"
                disabled={requisitionsQuery.isFetchingNextPage}
                onClick={() => void requisitionsQuery.fetchNextPage()}
              >
                {requisitionsQuery.isFetchingNextPage ? "Loading…" : "Load more requisitions"}
              </Button>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <h2 className="text-base font-semibold text-sr-text-blue">No requisitions yet</h2>
          <p className="mt-1 text-sm text-gray-500">Create a hiring request to begin your approval workflow.</p>
          <Button className="mt-4" asChild>
            <Link href="/dashboard/jobs/new">Create requisition</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
