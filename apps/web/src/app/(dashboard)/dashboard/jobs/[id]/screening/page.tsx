"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { useJobScreeningComparison } from "@/lib/api/hooks/application-screening";
import { useJobPosting } from "@/lib/api/hooks/jobs";

function formatAppliedDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatRating(value: number | null): string {
  return value === null ? "Not rated" : `${value.toFixed(1)} / 5`;
}

export default function JobScreeningComparisonPage() {
  const { id } = useParams<{ id: string }>();
  const { status } = useSession();
  const postingQuery = useJobPosting(id);
  const comparisonQuery = useJobScreeningComparison(id);
  const posting = postingQuery.data;
  const pages = comparisonQuery.data?.pages ?? [];
  const comparison = pages[0];
  const candidates = pages.flatMap((page) => page.items);
  const isLoading = status === "loading" || postingQuery.isLoading || comparisonQuery.isLoading;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
      <Link
        href={posting ? `/dashboard/jobs/${posting.id}` : "/dashboard/jobs"}
        className="text-sm font-medium text-gray-600 hover:text-sr-text-blue"
      >
        ← {posting ? "Back to job" : "Back to jobs"}
      </Link>

      <header className="flex flex-col gap-2">
        <p className="text-sm font-medium text-gray-500">Candidate screening</p>
        <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue sm:text-3xl">
          {posting ? `Compare candidates · ${posting.title}` : "Compare candidates"}
        </h1>
        <p className="max-w-3xl text-sm leading-6 text-gray-600">
          Review submitted scorecards against this job’s shared rubric. Ratings summarize reviewer input and do not make hiring decisions.
        </p>
      </header>

      {isLoading ? (
        <section className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500" aria-live="polite">
          Loading screening comparison…
        </section>
      ) : postingQuery.isError || comparisonQuery.isError ? (
        <section className="rounded-xl border border-red-200 bg-red-50 p-6" role="alert">
          <p className="text-sm text-red-800">We couldn’t load the screening comparison for this job.</p>
          <Button
            className="mt-4"
            variant="outline"
            onClick={() => void Promise.all([postingQuery.refetch(), comparisonQuery.refetch()])}
          >
            Try again
          </Button>
        </section>
      ) : !posting ? (
        <section className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600">
          This job posting isn’t available.
        </section>
      ) : !comparison?.rubric.length ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50 p-6">
          <h2 className="font-semibold text-amber-950">No screening rubric configured</h2>
          <p className="mt-2 text-sm leading-6 text-amber-900">
            Add a shared job-specific rubric before comparing screening scorecards.
          </p>
          <Button asChild className="mt-4" variant="outline">
            <Link href={`/dashboard/jobs/${posting.id}`}>Open job settings</Link>
          </Button>
        </section>
      ) : candidates.length === 0 ? (
        <section className="rounded-xl border border-gray-200 bg-white p-8 text-center sm:p-12">
          <h2 className="text-lg font-semibold text-sr-text-blue">No candidates in Screening</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-gray-600">
            Candidates appear here after their applications move to the Screening stage.
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-xl border border-gray-200 bg-white p-4 sm:p-5" aria-label="Current screening rubric">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-sr-text-blue">Shared rubric</h2>
              <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700">
                Version {comparison.rubric_version}
              </span>
            </div>
            <ul className="mt-3 flex flex-wrap gap-2">
              {comparison.rubric.map((criterion) => (
                <li key={criterion.id} className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700">
                  {criterion.criterion}
                </li>
              ))}
            </ul>
          </section>

          <div className="flex flex-col gap-4">
            {candidates.map((candidate) => (
              <article key={candidate.application_id} className="rounded-xl border border-gray-200 bg-white p-4 sm:p-6">
                <div className="flex flex-col gap-4 border-b border-gray-100 pb-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <Link
                      href={`/dashboard/applications/${candidate.application_id}`}
                      className="text-lg font-semibold text-sr-text-blue hover:underline"
                    >
                      {candidate.candidate_name}
                    </Link>
                    <p className="mt-1 text-sm text-gray-500">Applied {formatAppliedDate(candidate.applied_at)}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:min-w-80 sm:grid-cols-4">
                    <div>
                      <p className="text-xs text-gray-500">Average</p>
                      <p className="mt-1 text-sm font-semibold text-gray-900">{formatRating(candidate.average_overall_rating)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Current reviews</p>
                      <p className="mt-1 text-sm font-semibold text-gray-900">{candidate.current_rubric_review_count}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Advance</p>
                      <p className="mt-1 text-sm font-semibold text-gray-900">{candidate.advance_count}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Hold · Reject</p>
                      <p className="mt-1 text-sm font-semibold text-gray-900">{candidate.hold_count} · {candidate.reject_count}</p>
                    </div>
                  </div>
                </div>

                <div className="mt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Criterion ratings</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {candidate.criteria.map((criterion) => (
                      <div key={criterion.criterion_id} className="rounded-lg bg-gray-50 p-3">
                        <p className="text-sm font-medium text-gray-800">{criterion.criterion}</p>
                        <p className="mt-1 text-sm text-gray-600">{formatRating(criterion.average_rating)}</p>
                        <p className="mt-1 text-xs text-gray-500">{criterion.assessment_count} {criterion.assessment_count === 1 ? "rating" : "ratings"}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {candidate.previous_rubric_review_count > 0 && (
                  <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
                    {candidate.previous_rubric_review_count} earlier {candidate.previous_rubric_review_count === 1 ? "review used" : "reviews used"} a previous rubric version and are excluded from these averages.
                  </p>
                )}
              </article>
            ))}
          </div>

          {comparisonQuery.hasNextPage && (
            <div className="flex justify-center">
              <Button variant="outline" onClick={() => void comparisonQuery.fetchNextPage()} disabled={comparisonQuery.isFetchingNextPage}>
                {comparisonQuery.isFetchingNextPage ? "Loading…" : "Load more candidates"}
              </Button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
