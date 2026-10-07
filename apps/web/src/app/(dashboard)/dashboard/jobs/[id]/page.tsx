"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { JobStatusBadge } from "@/components/jobs/job-status-badge";
import {
  useJobPosting,
  usePublishJobPosting,
  useUnpublishJobPosting,
} from "@/lib/api/hooks/jobs";

export default function JobPostingPage() {
  const { id } = useParams<{ id: string }>();
  const { status: sessionStatus } = useSession();
  const postingQuery = useJobPosting(id);
  const publishMutation = usePublishJobPosting();
  const unpublishMutation = useUnpublishJobPosting();
  const posting = postingQuery.data;
  const isLoading = sessionStatus !== "authenticated" || postingQuery.isLoading;
  const isSaving = publishMutation.isPending || unpublishMutation.isPending;
  const error = publishMutation.error ?? unpublishMutation.error;

  function changePublication() {
    if (!posting) return;
    const variables = {
      id: posting.id,
      request: { expected_version: posting.version },
      idempotencyKey: crypto.randomUUID(),
    };
    if (posting.status === "published") {
      unpublishMutation.mutate(variables);
    } else {
      publishMutation.mutate(variables);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <Link href="/dashboard/jobs" className="text-sm font-medium text-gray-600 hover:text-sr-text-blue">
        ← Back to jobs
      </Link>

      {postingQuery.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
          We couldn’t load this job posting. Check your access and try again.
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
          {error instanceof Error ? error.message : "We couldn’t update this job posting."}
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading job posting…
        </div>
      ) : posting ? (
        <>
          <section className="rounded-xl border border-gray-200 bg-white p-6 sm:p-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">{posting.title}</h1>
                  <JobStatusBadge status={posting.status} />
                </div>
                <p className="text-sm text-gray-600">
                  {[posting.department, posting.location, posting.employment_type.replaceAll("_", " ")]
                    .filter(Boolean).join(" · ")}
                </p>
              </div>
              {posting.status !== "expired" && (
          <Button onClick={changePublication} disabled={isSaving}>
                  {isSaving
                    ? "Saving…"
                    : posting.status === "published"
                      ? "Unpublish job"
                      : "Publish job"}
                </Button>
              )}
            </div>

            <dl className="mt-8 grid gap-5 border-t border-gray-100 pt-6 sm:grid-cols-3">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(posting.created_at).toLocaleDateString()}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Last updated</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(posting.updated_at).toLocaleDateString()}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Expires</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {posting.expires_at ? new Date(posting.expires_at).toLocaleDateString() : "No expiry set"}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-gray-200 bg-white p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-sr-text-blue">Job description</h2>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-gray-700">{posting.description}</p>
          </section>
        </>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <p className="text-sm text-gray-600">This job posting isn’t available.</p>
          <Button className="mt-4" variant="outline" onClick={() => void postingQuery.refetch()}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
