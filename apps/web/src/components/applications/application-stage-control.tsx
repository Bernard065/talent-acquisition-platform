"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useTransitionApplicationStage } from "@/lib/api/hooks/applications";
import {
  ALLOWED_NEXT_APPLICATION_STAGES,
  APPLICATION_REJECTION_REASONS,
} from "@/lib/applications/stages";
import type { ApplicationRejectionReason, ApplicationStatus } from "@/types/api";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "New",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export function ApplicationStageControl({
  applicationId,
  status,
  version,
}: {
  applicationId: string;
  status: ApplicationStatus;
  version: number;
}) {
  const [pendingRejection, setPendingRejection] = useState(false);
  const [rejectionReason, setRejectionReason] = useState<ApplicationRejectionReason>("not_qualified");
  const [successMessage, setSuccessMessage] = useState("");
  const transitionMutation = useTransitionApplicationStage();
  const nextStages = ALLOWED_NEXT_APPLICATION_STAGES[status] ?? [];

  function transition(targetStatus: ApplicationStatus, reason?: ApplicationRejectionReason) {
    setSuccessMessage("");
    transitionMutation.mutate({
      id: applicationId,
      targetStatus,
      expectedVersion: version,
      rejectionReason: reason,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setPendingRejection(false);
        setSuccessMessage(`Application moved to ${STATUS_LABELS[targetStatus]}.`);
      },
    });
  }

  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <span className="w-fit rounded-full bg-sr-mint/60 px-3 py-1 text-sm font-semibold text-sr-text-blue">
        {STATUS_LABELS[status]}
      </span>
      {nextStages.length > 0 && (
        <label>
          <span className="sr-only">Move application to another stage</span>
          <select
            aria-label="Move application to another stage"
            value=""
            disabled={transitionMutation.isPending}
            onChange={(event) => {
              const targetStatus = event.target.value as ApplicationStatus;
              if (!targetStatus) return;
              setSuccessMessage("");
              if (targetStatus === "rejected") {
                setPendingRejection(true);
                return;
              }
              transition(targetStatus);
            }}
            className="h-10 cursor-pointer rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <option value="">Move to…</option>
            {nextStages.map((targetStatus) => (
              <option key={targetStatus} value={targetStatus}>
                {targetStatus === "rejected" ? "Reject application" : STATUS_LABELS[targetStatus]}
              </option>
            ))}
          </select>
        </label>
      )}
      {transitionMutation.isPending && <p className="text-xs text-gray-500" role="status">Updating stage…</p>}
      {transitionMutation.isError && (
        <p className="max-w-xs text-right text-xs text-red-800" role="alert">
          We couldn’t move this application. It may have changed; refresh and try again.
        </p>
      )}
      {successMessage && <p className="text-xs text-green-800" role="status">{successMessage}</p>}

      {pendingRejection && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/40 p-4" role="presentation">
          <section
            aria-labelledby="reject-application-heading"
            aria-modal="true"
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
            role="dialog"
          >
            <h2 id="reject-application-heading" className="text-lg font-semibold text-sr-text-blue">
              Reject this application?
            </h2>
            <p className="mt-2 text-sm text-gray-600">Choose a reason for the decision.</p>
            <label className="mt-5 block text-sm font-medium text-gray-700" htmlFor="application-rejection-reason">
              Rejection reason
            </label>
            <select
              id="application-rejection-reason"
              value={rejectionReason}
              onChange={(event) => setRejectionReason(event.target.value as ApplicationRejectionReason)}
              className="mt-2 h-10 w-full rounded-md border border-gray-200 bg-white px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              {APPLICATION_REJECTION_REASONS.map((reason) => (
                <option key={reason.value} value={reason.value}>{reason.label}</option>
              ))}
            </select>
            <div className="mt-6 flex justify-end gap-3">
              <Button type="button" variant="outline" disabled={transitionMutation.isPending} onClick={() => setPendingRejection(false)}>
                Cancel
              </Button>
              <Button type="button" variant="destructive" disabled={transitionMutation.isPending} onClick={() => transition("rejected", rejectionReason)}>
                {transitionMutation.isPending ? "Rejecting…" : "Confirm rejection"}
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
