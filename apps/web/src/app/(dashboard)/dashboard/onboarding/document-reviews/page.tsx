"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useSession } from "next-auth/react";
import {
  DocumentAccessButton,
  DocumentReviewControls,
} from "@/components/onboarding/onboarding-task-document-list";
import { useOnboardingDocumentReviewQueue } from "@/lib/api/hooks/onboarding";

const PAGE_SIZE = 20;

function fileSizeLabel(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function dateLabel(value: string | null): string {
  if (!value) return "Date unavailable";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

export default function OnboardingDocumentReviewsPage() {
  const { status: sessionStatus } = useSession();
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const params = useMemo(
    () => ({ page, limit: PAGE_SIZE, query: query || undefined }),
    [page, query],
  );
  const queue = useOnboardingDocumentReviewQueue(params);
  const items = queue.data?.items ?? [];
  const total = queue.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isLoading = sessionStatus === "loading" || queue.isLoading;

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(searchInput.trim());
    setPage(1);
  }

  function clearSearch() {
    setSearchInput("");
    setQuery("");
    setPage(1);
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header>
        <p className="text-sm font-semibold text-sr-green">Onboarding</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
          Document reviews
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-gray-600">
          Review employee documents after their security scan is complete. Accept
          a document or explain what needs to be replaced.
        </p>
      </header>

      <section className="rounded-xl border border-gray-200 bg-white p-4 sm:p-5" aria-label="Search document reviews">
        <form onSubmit={submitSearch} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs font-medium text-gray-600">
            Search by employee, job, task, or filename
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="For example, ID document or Benard"
              className="h-10 rounded-lg border border-gray-200 px-3 text-sm font-normal text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="submit"
              className="h-10 cursor-pointer rounded-lg bg-sr-green px-4 text-sm font-semibold text-white hover:brightness-95"
            >
              Search
            </button>
            {query && (
              <button
                type="button"
                onClick={clearSearch}
                className="h-10 cursor-pointer rounded-lg border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Clear
              </button>
            )}
          </div>
        </form>
      </section>

      <section aria-labelledby="review-queue-heading" className="overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div className="flex flex-col gap-1 border-b border-gray-200 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div>
            <h2 id="review-queue-heading" className="font-semibold text-sr-text-blue">
              Waiting for review
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              {isLoading ? "Loading review queue…" : `${total} ${total === 1 ? "document" : "documents"} pending`}
            </p>
          </div>
          <p className="text-xs text-gray-500">The queue refreshes automatically.</p>
        </div>

        {isLoading ? (
          <p className="px-5 py-12 text-center text-sm text-gray-600" role="status">
            Loading documents awaiting review…
          </p>
        ) : queue.isError ? (
          <div className="px-5 py-12 text-center">
            <p className="text-sm text-red-800" role="alert">
              We couldn’t load the onboarding document review queue.
            </p>
            <button
              type="button"
              onClick={() => void queue.refetch()}
              className="mt-3 cursor-pointer text-sm font-medium text-sr-text-blue underline"
            >
              Try again
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <h3 className="font-semibold text-sr-text-blue">
              {total > 0
                ? "This page no longer has pending documents"
                : query
                  ? "No documents match this search"
                  : "You’re all caught up"}
            </h3>
            <p className="mx-auto mt-2 max-w-lg text-sm text-gray-600">
              {total > 0
                ? "The queue changed while you were reviewing. Go to the last available page to continue."
                : query
                ? "Try another employee name, job title, task, or filename."
                : "Documents appear here after employees upload them and their security scans pass."}
            </p>
            {total > 0 ? (
              <button
                type="button"
                onClick={() => setPage(pageCount)}
                className="mt-4 cursor-pointer text-sm font-medium text-sr-text-blue underline"
              >
                Go to page {pageCount}
              </button>
            ) : query ? (
              <button
                type="button"
                onClick={clearSearch}
                className="mt-4 cursor-pointer text-sm font-medium text-sr-text-blue underline"
              >
                Clear search
              </button>
            ) : null}
          </div>
        ) : (
          <>
            <ul className="divide-y divide-gray-100">
              {items.map((item) => {
                const document = item.document;
                return (
                  <li key={document.id} className="p-4 sm:p-5">
                    <article className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <Link
                              href={`/dashboard/applications/${item.application_id}`}
                              className="font-semibold text-sr-text-blue hover:underline"
                            >
                              {item.employee_name}
                            </Link>
                            <p className="mt-0.5 text-sm text-gray-600">{item.job_title}</p>
                          </div>
                          <span className="shrink-0 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
                            Pending review
                          </span>
                        </div>

                        <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3 sm:p-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="min-w-0">
                              <p className="break-all text-sm font-semibold text-gray-900">
                                {document.original_filename}
                              </p>
                              <p className="mt-1 text-xs text-gray-600">
                                {item.task_title} · {fileSizeLabel(document.expected_byte_size)} · Uploaded {dateLabel(document.uploaded_at)}
                              </p>
                            </div>
                            <div className="flex shrink-0 gap-2">
                              {document.declared_content_type === "application/pdf" && (
                                <DocumentAccessButton document={document} mode="preview" />
                              )}
                              <DocumentAccessButton document={document} mode="download" />
                            </div>
                          </div>
                        </div>

                        <DocumentReviewControls document={document} canReview />
                      </div>
                      <Link
                        href={`/dashboard/applications/${item.application_id}`}
                        className="inline-flex min-h-9 items-center justify-center rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 lg:mt-1"
                      >
                        Open application
                      </Link>
                    </article>
                  </li>
                );
              })}
            </ul>

            <footer className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <p aria-live="polite" className="text-sm text-gray-600">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} documents
              </p>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  type="button"
                  disabled={page <= 1 || queue.isFetching}
                  onClick={() => setPage((current) => current - 1)}
                  className="h-9 cursor-pointer rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="px-1 text-sm text-gray-600">Page {page} of {pageCount}</span>
                <button
                  type="button"
                  disabled={page >= pageCount || queue.isFetching}
                  onClick={() => setPage((current) => current + 1)}
                  className="h-9 cursor-pointer rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
