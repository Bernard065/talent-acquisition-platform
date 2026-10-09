"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  useApproveRequisitionApproval,
  useAssignedRequisitionApproval,
  useRejectRequisitionApproval,
} from "@/lib/api/hooks/approvals";

function formatLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function RequisitionApprovalPage() {
  const { status: sessionStatus } = useSession();
  const { approvalId } = useParams<{ approvalId: string }>();
  const approvalQuery = useAssignedRequisitionApproval(approvalId);
  const approveMutation = useApproveRequisitionApproval();
  const rejectMutation = useRejectRequisitionApproval();
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const approval = approvalQuery.data;
  const isLoading = sessionStatus === "loading" || approvalQuery.isLoading;
  const isSaving = approveMutation.isPending || rejectMutation.isPending;

  async function decide(decision: "approve" | "reject") {
    if (!approval || !approval.is_current_approver) return;
    setActionError(null);
    setNotice(null);
    try {
      const variables = {
        approvalId: approval.approval_id,
        decision: { comment: comment.trim() || null },
        idempotencyKey: crypto.randomUUID(),
      };
      const result = decision === "approve"
        ? await approveMutation.mutateAsync(variables)
        : await rejectMutation.mutateAsync(variables);
      setNotice(
        decision === "approve"
          ? result.status === "approved"
            ? "Requisition approved."
            : "Your step is approved. The request has moved to the next approver."
          : "Requisition rejected and returned to draft.",
      );
      setComment("");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Could not record your decision.");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <Link href="/dashboard/approvals" className="w-fit text-sm font-medium text-sr-green hover:underline">
        ← Back to approvals
      </Link>

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading requisition…
        </div>
      ) : sessionStatus !== "authenticated" ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50 p-8">
          <h1 className="font-semibold text-amber-950">Sign in to view this requisition</h1>
        </section>
      ) : approvalQuery.isError || !approval ? (
        <section className="rounded-xl border border-gray-200 bg-white p-8">
          <h1 className="font-semibold text-sr-text-blue">Approval unavailable</h1>
          <p className="mt-2 text-sm text-gray-600">
            This requisition is unavailable or it isn’t assigned to your account.
          </p>
        </section>
      ) : (
        <>
          <header>
            <p className="text-sm font-medium text-sr-green">Requisition approval</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
              {approval.title}
            </h1>
            <p className="mt-2 text-sm text-gray-500">
              Submitted {formatDate(approval.submitted_at)} · {formatLabel(approval.approval_status)}
            </p>
          </header>

          <section className="grid gap-5 rounded-xl border border-gray-200 bg-white p-6 sm:grid-cols-2">
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Department</h2>
              <p className="mt-1 text-sm text-gray-900">{approval.department || "Not specified"}</p>
            </div>
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Location</h2>
              <p className="mt-1 text-sm text-gray-900">{approval.location || "Not specified"}</p>
            </div>
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Open positions</h2>
              <p className="mt-1 text-sm text-gray-900">{approval.headcount}</p>
            </div>
            {approval.description && (
              <div className="sm:col-span-2">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Description</h2>
                <p className="mt-1 whitespace-pre-wrap text-sm text-gray-900">{approval.description}</p>
              </div>
            )}
          </section>

          {notice && (
            <section role="status" className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-900">
              {notice} <Link href="/dashboard/approvals" className="font-semibold underline">Return to approvals</Link>
            </section>
          )}

          {approval.assigned_decision_status === "not_required" && (
            <section className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
              Another eligible reviewer completed this requisition’s approval. No action is needed.
            </section>
          )}

          {approval.approval_status === "pending" && !approval.is_current_approver && approval.assigned_decision_status !== "not_required" && (
            <section className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
              {approval.assigned_decision_status === "approved"
                ? "Your approval was recorded. The requisition is waiting for another eligible reviewer."
                : approval.assigned_step > approval.current_step
                  ? "Your approval step is coming up after the current approver finishes."
                  : "This approval is no longer on your active step."}
            </section>
          )}

          {approval.is_current_approver && (
            <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-sr-text-blue">Your decision</h2>
              <label htmlFor="approval-comment" className="mt-4 block text-sm font-medium text-gray-800">
                Comment <span className="font-normal text-gray-500">(optional)</span>
              </label>
              <textarea
                id="approval-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                maxLength={5000}
                rows={4}
                disabled={isSaving}
                className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-sr-green focus:outline-none focus:ring-2 focus:ring-sr-green/20"
              />
              {actionError && <p role="alert" className="mt-3 text-sm text-red-700">{actionError}</p>}
              <div className="mt-4 flex flex-wrap gap-3">
                <Button type="button" disabled={isSaving} onClick={() => void decide("approve")}>
                  {approveMutation.isPending ? "Approving…" : "Approve requisition"}
                </Button>
                <Button type="button" variant="outline" disabled={isSaving} onClick={() => void decide("reject")}>
                  {rejectMutation.isPending ? "Rejecting…" : "Reject and return to draft"}
                </Button>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
