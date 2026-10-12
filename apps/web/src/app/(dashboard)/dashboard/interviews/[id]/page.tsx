"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { InterviewFeedbackForm } from "@/components/interviews/interview-feedback-form";
import { useCancelInterview, useCompleteInterviewSession, useInterview } from "@/lib/api/hooks/interviews";
import { useApplicationSubmittedInterviewFeedback } from "@/lib/api/hooks/interview-feedback";
import {
  INTERVIEW_CANCELLATION_REASONS,
  type InterviewCancellationReason,
} from "@/types/api";

function formatLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "full",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function InterviewDetailsPage() {
  const { status: sessionStatus } = useSession();
  const { id } = useParams<{ id: string }>();
  const interviewQuery = useInterview(id);
  const submittedFeedbackQuery = useApplicationSubmittedInterviewFeedback(
    interviewQuery.data?.application_id ?? "",
    Boolean(interviewQuery.data?.application_id),
  );
  const cancelMutation = useCancelInterview();
  const completeMutation = useCompleteInterviewSession();
  const interview = interviewQuery.data;
  const isLoading = sessionStatus === "loading" || interviewQuery.isLoading;
  const [cancellationReason, setCancellationReason] = useState<InterviewCancellationReason | "">("");
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const [isConfirmingCompletion, setIsConfirmingCompletion] = useState(false);
  const hasSubmittedFeedback = Boolean(
    interview && submittedFeedbackQuery.data?.items.some(
      (feedback) => feedback.interview_session_id === interview.id,
    ),
  );
  const canComplete = Boolean(
    interview && (
      hasSubmittedFeedback || now >= new Date(interview.scheduled_end_at).getTime()
    ),
  );

  useEffect(() => {
    const updateNow = () => setNow(Date.now());
    updateNow();
    const intervalId = window.setInterval(updateNow, 30_000);
    return () => window.clearInterval(intervalId);
  }, []);

  async function cancel() {
    if (!interview || !cancellationReason) {
      setError("Choose a cancellation reason before continuing.");
      return;
    }
    setError(null);
    try {
      await cancelMutation.mutateAsync({
        interview,
        cancellationReason,
        idempotencyKey: crypto.randomUUID(),
      });
      setIsConfirming(false);
      setCancellationReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not cancel the interview.");
    }
  }

  async function complete() {
    if (!interview || !canComplete) return;
    setError(null);
    try {
      await completeMutation.mutateAsync({ interview, idempotencyKey: crypto.randomUUID() });
      setIsConfirmingCompletion(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not complete the interview.");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <Link
        href="/dashboard/interviews"
        className="w-fit text-sm font-medium text-gray-500 hover:text-sr-text-blue"
      >
        ← Back to interviews
      </Link>

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading interview…
        </div>
      ) : sessionStatus !== "authenticated" ? (
        <section role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
          <h1 className="font-semibold text-amber-950">Sign in to view this interview</h1>
          <Link className="mt-3 inline-block text-sm font-semibold text-sr-text-blue underline" href="/login">
            Go to sign in
          </Link>
        </section>
      ) : interviewQuery.isError || !interview ? (
        <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <h1 className="text-lg font-semibold text-red-900">Interview unavailable</h1>
          <p className="mt-2 text-sm text-red-800">This session may have been removed, or you may not have access to it.</p>
          <Button className="mt-5" variant="outline" onClick={() => void interviewQuery.refetch()}>
            Try again
          </Button>
        </section>
      ) : (
        <>
          <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-gray-500">Interview session</p>
                <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
                  {formatLabel(interview.status)} interview
                </h1>
              </div>
              <span className="rounded-full bg-gray-100 px-3 py-1 text-sm font-medium text-gray-700">
                {formatLabel(interview.status)}
              </span>
            </div>
          </header>

          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
            <h2 className="text-lg font-semibold text-sr-text-blue">Schedule</h2>
            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Starts</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  <time dateTime={interview.scheduled_start_at}>{formatDateTime(interview.scheduled_start_at)}</time>
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Ends</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  <time dateTime={interview.scheduled_end_at}>{formatDateTime(interview.scheduled_end_at)}</time>
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Application</dt>
                <dd className="mt-1">
                  <Link className="text-sm font-medium text-sr-text-blue underline" href={`/dashboard/applications/${interview.application_id}`}>
                    View application
                  </Link>
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Format</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {interview.format === "online"
                    ? "Online"
                    : interview.format === "in_person"
                      ? "In person"
                      : "Not specified"}
                </dd>
              </div>
              {interview.location && (
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Location</dt>
                  <dd className="mt-1 text-sm text-gray-900">{interview.location}</dd>
                </div>
              )}
              {interview.meeting_url && (
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Online interview</dt>
                  <dd className="mt-1">
                    <a className="text-sm font-semibold text-sr-text-blue underline" href={interview.meeting_url} target="_blank" rel="noopener noreferrer">
                      Join interview
                    </a>
                  </dd>
                </div>
              )}
              {interview.cancellation_reason && (
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Cancellation reason</dt>
                  <dd className="mt-1 text-sm text-gray-900">{formatLabel(interview.cancellation_reason)}</dd>
                </div>
              )}
            </dl>
            {interview.status === "scheduled" && (
              <div className="mt-8 border-t border-gray-100 pt-5">
                {canComplete ? (
                  <div className="mb-4 rounded-lg bg-blue-50 p-3">
                    <p className="text-sm text-blue-900">
                      {hasSubmittedFeedback
                        ? "Feedback has been submitted. Confirm the interview took place to mark it complete."
                        : "The scheduled end time has passed. Confirm the interview took place to mark it complete."}
                    </p>
                    <Button className="mt-3" disabled={completeMutation.isPending} onClick={() => { setError(null); setIsConfirmingCompletion(true); }}>
                      Mark interview complete
                    </Button>
                  </div>
                ) : (
                  <p className="mb-4 text-sm text-gray-600">
                    Submit interviewer feedback or wait until the scheduled end time to mark this interview complete.
                  </p>
                )}
                <Button variant="destructive" onClick={() => { setError(null); setIsConfirming(true); }}>
                  Cancel interview
                </Button>
              </div>
            )}
            {error && !isConfirming && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
          </section>

          <InterviewFeedbackForm
            sessionId={interview.id}
          />

        </>
      )}

      {isConfirming && interview?.status === "scheduled" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-interview-title"
            aria-describedby="cancel-interview-description"
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
          >
            <h2 id="cancel-interview-title" className="text-lg font-semibold text-gray-900">Cancel this interview?</h2>
            <p id="cancel-interview-description" className="mt-2 text-sm text-gray-600">
              The cancellation will be recorded in the interview schedule.
            </p>
            <label htmlFor="cancellation-reason" className="mt-4 block text-sm font-medium text-gray-700">
              Reason
            </label>
            <select
              id="cancellation-reason"
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              value={cancellationReason}
              onChange={(event) => setCancellationReason(event.target.value as InterviewCancellationReason | "")}
            >
              <option value="">Select a reason</option>
              {INTERVIEW_CANCELLATION_REASONS.map((reason) => (
                <option key={reason} value={reason}>{formatLabel(reason)}</option>
              ))}
            </select>
            {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" disabled={cancelMutation.isPending} onClick={() => { setIsConfirming(false); setCancellationReason(""); setError(null); }}>
                Keep interview
              </Button>
              <Button variant="destructive" disabled={cancelMutation.isPending || !cancellationReason} onClick={() => void cancel()}>
                {cancelMutation.isPending ? "Cancelling…" : "Confirm cancellation"}
              </Button>
            </div>
          </section>
        </div>
      )}
      {isConfirmingCompletion && interview?.status === "scheduled" && canComplete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <section role="dialog" aria-modal="true" aria-labelledby="complete-interview-title" className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h2 id="complete-interview-title" className="text-lg font-semibold text-gray-900">Mark interview complete?</h2>
            <p className="mt-2 text-sm text-gray-600">This records that the scheduled interview took place.</p>
            {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" disabled={completeMutation.isPending} onClick={() => { setIsConfirmingCompletion(false); setError(null); }}>Cancel</Button>
              <Button disabled={completeMutation.isPending} onClick={() => void complete()}>
                {completeMutation.isPending ? "Saving…" : "Confirm completion"}
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
