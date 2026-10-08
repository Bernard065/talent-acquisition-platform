"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { useInterviews } from "@/lib/api/hooks/interviews";
import type { InterviewSessionStatus } from "@/types/api";

const TABS: Array<{ status: InterviewSessionStatus; label: string }> = [
  { status: "scheduled", label: "Scheduled" },
  { status: "completed", label: "Completed" },
  { status: "cancelled", label: "Cancelled" },
];

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatDateTime(value: string): string {
  return dateTimeFormatter.format(new Date(value));
}

function formatLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function InterviewsPage() {
  const { status: sessionStatus } = useSession();
  const [activeStatus, setActiveStatus] = useState<InterviewSessionStatus>("scheduled");
  const interviewsQuery = useInterviews({ status: activeStatus, limit: 25 });
  const interviews = interviewsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const isLoading = sessionStatus === "loading" || interviewsQuery.isLoading;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Interviews</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review interview sessions for your workspace.
        </p>
      </header>

      <div className="border-b border-gray-200">
        <nav aria-label="Filter interviews by status" className="flex gap-6 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.status}
              type="button"
              aria-pressed={activeStatus === tab.status}
              onClick={() => setActiveStatus(tab.status)}
              className={`border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                activeStatus === tab.status
                  ? "border-sr-green text-sr-text-blue"
                  : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading interviews…
        </div>
      ) : sessionStatus !== "authenticated" ? (
        <section role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
          <h2 className="font-semibold text-amber-950">Sign in to view interviews</h2>
          <Link className="mt-3 inline-block text-sm font-semibold text-sr-text-blue underline" href="/login">
            Go to sign in
          </Link>
        </section>
      ) : interviewsQuery.isError ? (
        <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <h2 className="font-semibold text-red-900">Interviews couldn’t be loaded</h2>
          <p className="mt-2 text-sm text-red-800">Check your connection and try again.</p>
          <Button className="mt-5" variant="outline" onClick={() => void interviewsQuery.refetch()}>
            Try again
          </Button>
        </section>
      ) : interviews.length === 0 ? (
        <section className="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center">
          <h2 className="text-lg font-semibold text-sr-text-blue">
            No {activeStatus} interviews
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Interviews in this status will appear here when they’re available.
          </p>
        </section>
      ) : (
        <>
          <ul className="space-y-4">
            {interviews.map((interview) => (
              <li key={interview.id}>
                <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h2 className="font-semibold text-sr-text-blue">Interview session</h2>
                      <p className="mt-1 text-sm text-gray-600">
                        Starts <time dateTime={interview.scheduled_start_at}>{formatDateTime(interview.scheduled_start_at)}</time>
                      </p>
                      <p className="mt-1 text-sm text-gray-600">
                        Ends <time dateTime={interview.scheduled_end_at}>{formatDateTime(interview.scheduled_end_at)}</time>
                      </p>
                    </div>
                    <span className="inline-flex w-fit items-center rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700">
                      {formatLabel(interview.status)}
                    </span>
                  </div>

                  <dl className="mt-5 grid gap-4 border-t border-gray-100 pt-4 sm:grid-cols-2">
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Participants</dt>
                      <dd className="mt-1 text-sm text-gray-900">
                        {interview.participants.length === 0
                          ? "No participants listed"
                          : interview.participants
                              .map((participant) => formatLabel(participant.role))
                              .join(", ")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Application</dt>
                      <dd className="mt-1">
                        <Link
                          className="text-sm font-medium text-sr-text-blue underline underline-offset-2 hover:text-sr-green"
                          href={`/dashboard/applications/${interview.application_id}`}
                        >
                          View application
                        </Link>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Details</dt>
                      <dd className="mt-1">
                        <Link
                          className="text-sm font-medium text-sr-text-blue underline underline-offset-2 hover:text-sr-green"
                          href={`/dashboard/interviews/${interview.id}`}
                        >
                          View interview
                        </Link>
                      </dd>
                    </div>
                    {interview.cancellation_reason && (
                      <div>
                        <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Cancellation reason</dt>
                        <dd className="mt-1 text-sm text-gray-900">
                          {formatLabel(interview.cancellation_reason)}
                        </dd>
                      </div>
                    )}
                  </dl>
                </article>
              </li>
            ))}
          </ul>

          {interviewsQuery.hasNextPage && (
            <Button
              variant="outline"
              disabled={interviewsQuery.isFetchingNextPage}
              onClick={() => void interviewsQuery.fetchNextPage()}
              className="self-center"
            >
              {interviewsQuery.isFetchingNextPage ? "Loading…" : "Load more interviews"}
            </Button>
          )}
          {interviewsQuery.isFetchNextPageError && (
            <p role="alert" className="text-center text-sm text-red-700">
              Could not load more interviews. Use the button above to retry.
            </p>
          )}
        </>
      )}
    </div>
  );
}
