"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { RequisitionEditDialog } from "@/components/requisitions/requisition-edit-dialog";
import {
  useCreateJobPostingFromRequisition,
  useJobPostings,
} from "@/lib/api/hooks/jobs";
import {
  useRequisitions,
  useSubmitRequisitionForApproval,
  useTransitionRequisition,
} from "@/lib/api/hooks/requisitions";
import { useCurrentIdentity } from "@/lib/api/hooks/auth";
import { useApprovalPolicyConfiguration } from "@/lib/api/hooks/approvals";
import { BriefcaseBusiness, LoaderCircle, Pencil, Send } from "@/components/icons";
import type { EmploymentType } from "@/types/api/jobs";
import type { RequisitionResponse, RequisitionStatus } from "@/types/api/requisitions";

const employmentTypes: { value: EmploymentType; label: string }[] = [
  { value: "full_time", label: "Full time" },
  { value: "part_time", label: "Part time" },
  { value: "contract", label: "Contract" },
  { value: "temporary", label: "Temporary" },
  { value: "internship", label: "Internship" },
];

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

function getLocalDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getTomorrowDateInputValue() {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return getLocalDateInputValue(tomorrow);
}

export default function RequisitionsPage() {
  const router = useRouter();
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedRequisitionId, setSelectedRequisitionId] = useState<string | null>(null);
  const [editingRequisition, setEditingRequisition] = useState<RequisitionResponse | null>(null);
  const [employmentType, setEmploymentType] = useState<EmploymentType>("full_time");
  const [expiryDate, setExpiryDate] = useState("");
  const { status: sessionStatus } = useSession();
  const identityQuery = useCurrentIdentity();
  const approvalPolicyQuery = useApprovalPolicyConfiguration();
  const currentSubject = identityQuery.data?.subject;
  const roles = identityQuery.data?.roles ?? [];
  const isWorkspaceAdmin = roles.includes("tenant_admin");
  const canSetUpInitialApprovalPolicy = !isWorkspaceAdmin
    && roles.includes("recruiter")
    && approvalPolicyQuery.data?.default_policy === null;
  const canOpenRequisition = roles.some((role) => ["tenant_admin", "recruiter"].includes(role));
  const canManageJobPostings = roles.some((role) =>
    ["tenant_admin", "recruiter", "hiring_manager"].includes(role),
  );
  const requisitionsQuery = useRequisitions({ limit: 100 });
  const postingsQuery = useJobPostings({ limit: 100 });
  const submitMutation = useSubmitRequisitionForApproval();
  const transitionMutation = useTransitionRequisition();
  const createPostingMutation = useCreateJobPostingFromRequisition();
  const requisitions = requisitionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const postings = postingsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const postingsByRequisition = new Map(postings.map((posting) => [posting.requisition_id, posting]));
  const isLoading = sessionStatus !== "authenticated"
    || requisitionsQuery.isLoading
    || postingsQuery.isLoading;
  const error = requisitionsQuery.isError || postingsQuery.isError
    ? "We couldn’t load requisitions and their job postings from your workspace. Please try again."
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

  async function createJobPosting() {
    if (!selectedRequisitionId) return;
    setActionError(null);

    try {
      const requisition = requisitions.find((item) => item.id === selectedRequisitionId);
      if (!requisition) throw new Error("This requisition is no longer available. Refresh and try again.");

      if (requisition.status === "approved") {
        await transitionMutation.mutateAsync({
          id: requisition.id,
          transition: { target_status: "open" },
          idempotencyKey: crypto.randomUUID(),
        });
      }

      const posting = await createPostingMutation.mutateAsync({
        requisitionId: selectedRequisitionId,
        request: {
          employment_type: employmentType,
          expires_at: expiryDate
            ? new Date(`${expiryDate}T23:59:59`).toISOString()
            : null,
        },
        idempotencyKey: crypto.randomUUID(),
      });
      setSelectedRequisitionId(null);
      setExpiryDate("");
      router.push(`/dashboard/jobs/${posting.id}`);
    } catch (cause) {
      setActionError(
        cause instanceof Error
          ? cause.message
          : "We couldn’t create a job posting from this requisition.",
      );
      await Promise.all([
        requisitionsQuery.refetch(),
        postingsQuery.refetch(),
      ]);
    }
  }

  const isCreatingPosting = transitionMutation.isPending || createPostingMutation.isPending;

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
          {canSetUpInitialApprovalPolicy && (
            <Button asChild variant="outline">
              <Link href="/dashboard/settings/approvals">Set up approval policy</Link>
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
          <div className="hidden grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_minmax(5.5rem,auto)] gap-4 border-b border-gray-100 bg-gray-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid">
            <span>Role</span><span>Department</span><span>Openings</span><span>Status</span><span className="text-right">Actions</span>
          </div>
          <ul className="divide-y divide-gray-100">
            {requisitions.map((requisition) => {
              const existingPosting = postingsByRequisition.get(requisition.id);
              const isCreator = requisition.created_by_subject === currentSubject;
              const canEditRequisition = isCreator;
              const canCreatePosting = canManageJobPostings
                || (isCreator && ["approved", "open"].includes(requisition.status));
              const canOpenThisRequisition = canOpenRequisition || isCreator;
              return (
              <li key={requisition.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_minmax(5.5rem,auto)] md:items-center md:gap-4">
                <div className="min-w-0">
                  <h2 className="truncate font-semibold text-sr-text-blue">{requisition.title}</h2>
                  <p className="mt-1 truncate text-sm text-gray-500">
                    {[requisition.location, new Date(requisition.created_at).toLocaleDateString()]
                      .filter(Boolean).join(" · ")}
                  </p>
                  {requisition.status === "draft" && requisition.latest_rejection_at && (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">
                        Reviewer requested changes · {new Date(requisition.latest_rejection_at).toLocaleDateString()}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-amber-950">
                        {requisition.latest_rejection_comment?.trim()
                          || "The approver didn’t leave a comment. Contact them for guidance before resubmitting."}
                      </p>
                    </div>
                  )}
                </div>
                <div className="text-sm text-gray-700">{requisition.department ?? "—"}</div>
                <div className="text-sm text-gray-700">{requisition.headcount}</div>
                <div>
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle[requisition.status]}`}>
                    {formatStatus(requisition.status)}
                  </span>
                </div>
                <div className="flex items-center justify-start gap-2 md:justify-end">
                  {requisition.status === "draft" ? (
                    <>
                      {canEditRequisition && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-9 w-9 rounded-lg border border-gray-200 bg-white p-0 text-gray-600 hover:bg-gray-50 hover:text-sr-text-blue"
                          aria-label={`Edit ${requisition.title}`}
                          title="Edit requisition"
                          onClick={() => setEditingRequisition(requisition)}
                        >
                          <Pencil className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      )}
                      {isCreator && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-9 w-9 rounded-lg border border-gray-200 bg-white p-0 text-gray-600 hover:bg-gray-50 hover:text-sr-text-blue"
                          aria-label={`Submit ${requisition.title} for approval`}
                          title="Submit for approval"
                          disabled={submitMutation.isPending}
                          onClick={() => void submitForApproval(requisition.id)}
                        >
                          {submitMutation.isPending
                            && submitMutation.variables?.requisitionId === requisition.id
                            ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                            : <Send className="h-4 w-4" aria-hidden="true" />}
                        </Button>
                      )}
                    </>
                  ) : requisition.status === "pending_approval" ? (
                    <span className="text-sm text-gray-500">Awaiting approval</span>
                  ) : requisition.status === "approved" || requisition.status === "open" ? (
                    !existingPosting && canCreatePosting
                      && (requisition.status === "open" || canOpenThisRequisition) ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9 rounded-lg border border-gray-200 bg-white p-0 text-gray-600 hover:bg-gray-50 hover:text-sr-text-blue"
                        aria-label={`Create job posting from ${requisition.title}`}
                        title="Create job posting"
                        onClick={() => {
                          setActionError(null);
                          setEmploymentType("full_time");
                          setExpiryDate("");
                          setSelectedRequisitionId(requisition.id);
                        }}
                      >
                        <BriefcaseBusiness className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    ) : null
                  ) : null}
                </div>
              </li>
              );
            })}
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

      {editingRequisition && (
        <RequisitionEditDialog
          key={editingRequisition.id}
          requisition={editingRequisition}
          onClose={() => setEditingRequisition(null)}
        />
      )}

      {selectedRequisitionId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !isCreatingPosting) {
              setSelectedRequisitionId(null);
            }
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-job-posting-title"
            className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl"
          >
            <h2 id="create-job-posting-title" className="text-lg font-semibold text-sr-text-blue">
              Create job posting
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              This creates a draft job posting from the requisition. If it is approved, it will be opened for recruiting first. You can review and publish the posting next.
            </p>
            <label htmlFor="employment-type" className="mt-5 block text-sm font-medium text-gray-700">
              Employment type
            </label>
            <select
              id="employment-type"
              value={employmentType}
              onChange={(event) => setEmploymentType(event.target.value as EmploymentType)}
              disabled={isCreatingPosting}
              className="mt-1 h-11 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
            >
              {employmentTypes.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            <label htmlFor="job-posting-expiry" className="mt-4 block text-sm font-medium text-gray-700">
              Expiry date <span className="font-normal text-gray-500">(optional)</span>
            </label>
            <input
              id="job-posting-expiry"
              type="date"
              min={getTomorrowDateInputValue()}
              value={expiryDate}
              onChange={(event) => setExpiryDate(event.target.value)}
              disabled={isCreatingPosting}
              className="mt-1 h-11 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green"
            />
            <p className="mt-1 text-xs text-gray-500">
              The job remains open through the end of this date in your local time. Leave blank for no expiry.
            </p>
            {actionError && (
              <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                {actionError}
              </p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                disabled={isCreatingPosting}
                onClick={() => setSelectedRequisitionId(null)}
              >
                Cancel
              </Button>
              <Button type="button" disabled={isCreatingPosting} onClick={() => void createJobPosting()}>
                {isCreatingPosting ? "Creating…" : "Create draft posting"}
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
