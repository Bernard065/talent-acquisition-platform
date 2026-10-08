"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { useRequisitions } from "@/lib/api/hooks/requisitions";
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
  const { status: sessionStatus } = useSession();
  const requisitionsQuery = useRequisitions({ limit: 100 });
  const requisitions = requisitionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const isLoading = sessionStatus !== "authenticated" || requisitionsQuery.isLoading;
  const error = requisitionsQuery.isError
    ? "We couldn’t load requisitions from your workspace. Please try again."
    : null;

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Requisitions</h1>
          <p className="mt-1 text-sm text-gray-500">Plan and track hiring requests through approval.</p>
        </div>
        <Button asChild>
          <Link href="/dashboard/jobs/new">Create requisition</Link>
        </Button>
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
          <div className="hidden grid-cols-[minmax(0,2fr)_1fr_1fr_1fr] gap-4 border-b border-gray-100 bg-gray-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid">
            <span>Role</span><span>Department</span><span>Openings</span><span>Status</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {requisitions.map((requisition) => (
              <li key={requisition.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr] md:items-center md:gap-4">
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
