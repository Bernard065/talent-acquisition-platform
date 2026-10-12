"use client";

import { Button } from "@/components/ui/button";
import { useApplicationSubmittedInterviewFeedback } from "@/lib/api/hooks/interview-feedback";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatRecommendation(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function ApplicationInterviewFeedbackSection({
  applicationId,
}: {
  applicationId: string;
}) {
  const feedbackQuery = useApplicationSubmittedInterviewFeedback(applicationId);
  const feedbackItems = feedbackQuery.data?.items ?? [];

  return (
    <section
      aria-labelledby="application-interview-feedback-heading"
      className="rounded-xl border border-gray-200 bg-white p-6"
    >
      <div>
        <h2
          id="application-interview-feedback-heading"
          className="text-base font-semibold text-sr-text-blue"
        >
          Interview feedback
        </h2>
        <p className="mt-1 text-sm text-gray-600">
          Submitted assessments from the interview panel. Draft feedback remains private to its author.
        </p>
      </div>

      {feedbackQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">
          Loading interview feedback…
        </p>
      ) : feedbackQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">
            We couldn’t load submitted interview feedback for this application.
          </p>
          <Button type="button" variant="outline" onClick={() => void feedbackQuery.refetch()}>
            Try again
          </Button>
        </div>
      ) : feedbackItems.length === 0 ? (
        <p className="mt-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
          No interview feedback has been submitted yet.
        </p>
      ) : (
        <ul className="mt-4 space-y-4">
          {feedbackItems.map((feedback) => (
            <li key={feedback.id} className="rounded-lg border border-gray-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    {feedback.interviewer_display_name}
                  </h3>
                  <p className="mt-1 text-sm text-gray-600">
                    Interview {formatDate(feedback.scheduled_start_at)}
                    {` · Submitted ${formatDate(feedback.submitted_at)}`}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800">
                    {feedback.overall_rating}/5 rating
                  </span>
                  <span className="rounded-full bg-sr-mint/60 px-2.5 py-1 text-xs font-medium text-sr-text-blue">
                    {formatRecommendation(feedback.recommendation)}
                  </span>
                </div>
              </div>

              {(feedback.strengths || feedback.concerns) && (
                <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                  {feedback.strengths && (
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Strengths
                      </dt>
                      <dd className="mt-1 whitespace-pre-wrap text-sm text-gray-800">
                        {feedback.strengths}
                      </dd>
                    </div>
                  )}
                  {feedback.concerns && (
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                        Concerns
                      </dt>
                      <dd className="mt-1 whitespace-pre-wrap text-sm text-gray-800">
                        {feedback.concerns}
                      </dd>
                    </div>
                  )}
                </dl>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
