"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  useApplicationSubmittedInterviewFeedback,
} from "@/lib/api/hooks/interview-feedback";
import {
  useApplicationHiringDecision,
  useRecordApplicationHiringDecision,
} from "@/lib/api/hooks/hiring-decisions";
import type {
  ApplicationRejectionReason,
  ApplicationResponse,
  HiringDecision,
} from "@/types/api/applications";

const RECOMMENDATION_LABELS = {
  strong_no: "Strong no",
  no: "No",
  yes: "Yes",
  strong_yes: "Strong yes",
} as const;

const REJECTION_REASON_LABELS: Record<ApplicationRejectionReason, string> = {
  not_qualified: "Does not meet role requirements",
  better_matched_candidate: "Another candidate was a stronger match",
  failed_assessment: "Did not meet assessment criteria",
  compensation_mismatch: "Compensation expectations did not align",
  role_closed: "Role is no longer open",
  other: "Other",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function ApplicationDebriefSection({
  application,
  canReview,
}: {
  application: ApplicationResponse;
  canReview: boolean;
}) {
  const [decision, setDecision] = useState<HiringDecision>("advance_to_offer");
  const [rationale, setRationale] = useState("");
  const [rejectionReason, setRejectionReason] = useState<ApplicationRejectionReason | "">("");
  const [error, setError] = useState<string | null>(null);
  const feedbackQuery = useApplicationSubmittedInterviewFeedback(application.id, canReview);
  const decisionQuery = useApplicationHiringDecision(application.id, canReview);
  const recordDecision = useRecordApplicationHiringDecision();
  const feedbackItems = feedbackQuery.data?.items ?? [];
  const recordedDecision = decisionQuery.data?.decision;

  async function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rationale.trim() || (decision === "reject" && !rejectionReason)) {
      setError("Add a rationale and choose a rejection reason when rejecting the application.");
      return;
    }
    setError(null);
    try {
      await recordDecision.mutateAsync({
        applicationId: application.id,
        decision: {
          decision,
          expected_application_version: application.version,
          rationale: rationale.trim(),
          rejection_reason: decision === "reject" ? rejectionReason || null : null,
        },
        idempotencyKey: crypto.randomUUID(),
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not record the hiring outcome.");
    }
  }

  if (!canReview) return null;

  const isLoading = feedbackQuery.isLoading || decisionQuery.isLoading;
  const isError = feedbackQuery.isError || decisionQuery.isError;

  return (
    <section aria-labelledby="application-debrief-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-debrief-heading" className="text-base font-semibold text-sr-text-blue">Interview debrief</h2>
        <p className="mt-1 text-sm text-gray-600">Review submitted interviewer feedback and record the hiring outcome.</p>
      </div>
      {isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading interview debrief…</p>
      ) : isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">We couldn’t load the interview debrief.</p>
          <Button type="button" variant="outline" onClick={() => { void feedbackQuery.refetch(); void decisionQuery.refetch(); }}>Try again</Button>
        </div>
      ) : (
        <>
          {recordedDecision ? (
            <div className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-sm font-semibold text-blue-950">
                {recordedDecision.decision === "advance_to_offer" ? "Outcome: Advance to offer" : "Outcome: Rejected"}
              </p>
              <p className="mt-1 text-xs text-blue-900">Recorded {formatDate(recordedDecision.decided_at)}</p>
              {recordedDecision.rejection_reason && (
                <p className="mt-3 text-sm text-blue-950">Reason: {REJECTION_REASON_LABELS[recordedDecision.rejection_reason]}</p>
              )}
              <p className="mt-3 whitespace-pre-wrap text-sm text-blue-950">{recordedDecision.rationale}</p>
            </div>
          ) : null}

          <div className="mt-5">
            <h3 className="text-sm font-semibold text-gray-900">Submitted interviewer feedback</h3>
            {!feedbackItems.length ? (
              <p className="mt-2 text-sm text-gray-600">No feedback has been submitted for this application yet.</p>
            ) : (
              <ol className="mt-3 space-y-3">
                {feedbackItems.map((item) => (
                  <li key={item.id} className="rounded-lg border border-gray-200 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{item.interviewer_display_name}</p>
                        <p className="mt-1 text-xs text-gray-500">
                          Interview {formatDate(item.scheduled_start_at)} · Feedback submitted {formatDate(item.submitted_at)}
                        </p>
                      </div>
                      <span className="rounded-full bg-sr-mint/60 px-2.5 py-1 text-xs font-semibold text-sr-text-blue">
                        {item.overall_rating}/5 · {RECOMMENDATION_LABELS[item.recommendation]}
                      </span>
                    </div>
                    {item.strengths && <p className="mt-3 whitespace-pre-wrap text-sm text-gray-700"><strong>Strengths:</strong> {item.strengths}</p>}
                    {item.concerns && <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700"><strong>Concerns:</strong> {item.concerns}</p>}
                  </li>
                ))}
              </ol>
            )}
          </div>

          {!recordedDecision && application.status === "interview" && feedbackItems.length > 0 && (
            <form className="mt-6 border-t border-gray-100 pt-5" onSubmit={submitDecision}>
              <h3 className="text-sm font-semibold text-gray-900">Record hiring outcome</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="mb-1 block text-sm font-medium text-gray-700">Outcome</span>
                  <select value={decision} onChange={(event) => { setDecision(event.target.value as HiringDecision); setError(null); }} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                    <option value="advance_to_offer">Advance to offer</option>
                    <option value="reject">Reject application</option>
                  </select>
                </label>
                {decision === "reject" && (
                  <label>
                    <span className="mb-1 block text-sm font-medium text-gray-700">Rejection reason</span>
                    <select required value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value as ApplicationRejectionReason | "")} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
                      <option value="">Choose a reason</option>
                      {Object.entries(REJECTION_REASON_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                )}
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-gray-700">Decision rationale</span>
                  <textarea required minLength={1} maxLength={5000} rows={4} value={rationale} onChange={(event) => setRationale(event.target.value)} className="w-full rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="Summarize the debrief and explain the decision." />
                </label>
              </div>
              {error && <p className="mt-3 text-sm text-red-800" role="alert">{error}</p>}
              <Button className="mt-4" type="submit" disabled={recordDecision.isPending || !rationale.trim() || (decision === "reject" && !rejectionReason)}>
                {recordDecision.isPending ? "Recording outcome…" : "Record outcome"}
              </Button>
              <p className="mt-2 text-xs text-gray-500">Recording an outcome moves this application to Offer or Rejected.</p>
            </form>
          )}
          {!recordedDecision && application.status === "interview" && feedbackItems.length === 0 && (
            <p className="mt-5 border-t border-gray-100 pt-4 text-sm text-gray-600">At least one interviewer must submit feedback before you can record an outcome.</p>
          )}
          {error && !feedbackItems.length && <p className="mt-3 text-sm text-red-800" role="alert">{error}</p>}
        </>
      )}
    </section>
  );
}
