"use client";

import { useState, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import {
  useCreateInterviewFeedbackDraft,
  useMyInterviewFeedback,
  useSubmitInterviewFeedback,
  useUpdateInterviewFeedbackDraft,
} from "@/lib/api/hooks/interview-feedback";
import type { InterviewFeedback, InterviewRecommendation } from "@/types/api";

const RECOMMENDATIONS: Record<InterviewRecommendation, string> = {
  strong_no: "Strong no",
  no: "No",
  yes: "Yes",
  strong_yes: "Strong yes",
};

function FeedbackEditor({
  sessionId,
  feedback,
}: {
  sessionId: string;
  feedback: InterviewFeedback | null;
}) {
  const [rating, setRating] = useState(feedback?.overall_rating?.toString() ?? "");
  const [recommendation, setRecommendation] = useState<InterviewRecommendation | "">(feedback?.recommendation ?? "");
  const [strengths, setStrengths] = useState(feedback?.strengths ?? "");
  const [concerns, setConcerns] = useState(feedback?.concerns ?? "");
  const [error, setError] = useState<string | null>(null);
  const createDraft = useCreateInterviewFeedbackDraft();
  const updateDraft = useUpdateInterviewFeedbackDraft();
  const submitFeedback = useSubmitInterviewFeedback();
  const isPending = createDraft.isPending || updateDraft.isPending || submitFeedback.isPending;

  function values() {
    return {
      overall_rating: rating ? Number(rating) : null,
      recommendation: recommendation || null,
      strengths: strengths.trim() || null,
      concerns: concerns.trim() || null,
    };
  }

  async function saveDraft() {
    setError(null);
    const body = values();
    if (feedback) {
      await updateDraft.mutateAsync({
        sessionId,
        feedbackId: feedback.id,
        feedback: { ...body, expected_version: feedback.version },
        idempotencyKey: crypto.randomUUID(),
      });
    } else {
      await createDraft.mutateAsync({
        sessionId,
        feedback: body,
        idempotencyKey: crypto.randomUUID(),
      });
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!rating || !recommendation) {
      setError("Choose an overall rating and recommendation before submitting.");
      return;
    }

    try {
      let draft = feedback;
      if (!draft) {
        draft = await createDraft.mutateAsync({
          sessionId,
          feedback: values(),
          idempotencyKey: crypto.randomUUID(),
        });
      }
      await submitFeedback.mutateAsync({
        sessionId,
        feedbackId: draft.id,
        feedback: {
          ...values(),
          overall_rating: Number(rating),
          recommendation,
          expected_version: draft.version,
        },
        idempotencyKey: crypto.randomUUID(),
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit interview feedback.");
    }
  }

  return (
    <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Overall rating</span>
        <select required value={rating} onChange={(event) => setRating(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
          <option value="">Choose rating</option>
          {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}
        </select>
      </label>
      <label>
        <span className="mb-1 block text-sm font-medium text-gray-700">Recommendation</span>
        <select required value={recommendation} onChange={(event) => setRecommendation(event.target.value as InterviewRecommendation | "")} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm">
          <option value="">Choose recommendation</option>
          {Object.entries(RECOMMENDATIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-gray-700">Strengths</span>
        <textarea value={strengths} onChange={(event) => setStrengths(event.target.value)} maxLength={5000} rows={4} className="w-full rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="What did the candidate do well?" />
      </label>
      <label className="sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-gray-700">Concerns</span>
        <textarea value={concerns} onChange={(event) => setConcerns(event.target.value)} maxLength={5000} rows={4} className="w-full rounded-lg border border-gray-200 p-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" placeholder="What risks or gaps should the hiring team consider?" />
      </label>
      {error && <p className="sm:col-span-2 text-sm text-red-800" role="alert">{error}</p>}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button type="button" variant="outline" disabled={isPending} onClick={() => void saveDraft().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not save this draft."))}>
          {isPending ? "Saving…" : "Save draft"}
        </Button>
        <Button type="submit" disabled={isPending || !rating || !recommendation}>
          {submitFeedback.isPending ? "Submitting…" : "Submit feedback"}
        </Button>
      </div>
      <p className="sm:col-span-2 text-xs text-gray-500">Submitted feedback is final and visible to authorized recruiting team members.</p>
    </form>
  );
}

export function InterviewFeedbackForm({
  sessionId,
}: {
  sessionId: string;
}) {
  const { data: session } = useSession();
  const isInterviewer = session?.roles?.includes("interviewer") ?? false;
  const feedbackQuery = useMyInterviewFeedback(sessionId, isInterviewer);

  if (!isInterviewer) return null;

  return (
    <section aria-labelledby="interview-feedback-heading" className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
      <h2 id="interview-feedback-heading" className="text-lg font-semibold text-sr-text-blue">Your interview feedback</h2>
      <p className="mt-1 text-sm text-gray-600">Your draft stays private. Once submitted, it can be reviewed by the recruiting team.</p>
      {feedbackQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading your feedback…</p>
      ) : feedbackQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">
            {feedbackQuery.error instanceof ApiError && feedbackQuery.error.isForbidden
              ? "Feedback is available only to interviewers assigned to this session."
              : "We couldn’t load your feedback for this session."}
          </p>
          <Button type="button" variant="outline" onClick={() => void feedbackQuery.refetch()}>Try again</Button>
        </div>
      ) : feedbackQuery.data?.feedback?.status === "submitted" ? (
        <div className="mt-4 rounded-lg border border-green-200 bg-green-50 p-4">
          <p className="text-sm font-semibold text-green-900">Feedback submitted</p>
          <p className="mt-1 text-sm text-green-900">
            {feedbackQuery.data.feedback.overall_rating} / 5 · {feedbackQuery.data.feedback.recommendation ? RECOMMENDATIONS[feedbackQuery.data.feedback.recommendation] : "Recommendation submitted"}
          </p>
          {feedbackQuery.data.feedback.submitted_at && <p className="mt-1 text-xs text-green-800">Submitted {new Date(feedbackQuery.data.feedback.submitted_at).toLocaleString()}</p>}
        </div>
      ) : feedbackQuery.data ? (
        <FeedbackEditor
          key={feedbackQuery.data.feedback?.id ?? "new-feedback"}
          sessionId={sessionId}
          feedback={feedbackQuery.data.feedback}
        />
      ) : null}
    </section>
  );
}
