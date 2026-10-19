"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import {
  useOnboardingTaskDocumentDownload,
  useOnboardingTaskDocumentPreview,
  useReviewOnboardingTaskDocument,
} from "@/lib/api/hooks/onboarding";
import type { OnboardingTaskDocumentResponse } from "@/types/api/onboarding";

function fileSizeLabel(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function documentStatusLabel(status: OnboardingTaskDocumentResponse["status"]): string {
  if (status === "available") return "Ready to view";
  if (status === "quarantined") return "Blocked by security scan";
  if (status === "rejected") return "Upload could not be verified";
  if (status === "pending_upload") return "Upload not finished";
  if (status === "uploaded") return "Waiting for security scan";
  return "Security scan in progress";
}

function reviewStatusLabel(status: OnboardingTaskDocumentResponse["review_status"]): string {
  if (status === "pending_review") return "Awaiting People Operations review";
  if (status === "accepted") return "Accepted by People Operations";
  if (status === "changes_requested") return "Replacement requested";
  return "Review not required";
}

export function DocumentReviewControls({
  document,
  canReview,
}: {
  document: OnboardingTaskDocumentResponse;
  canReview: boolean;
}) {
  const review = useReviewOnboardingTaskDocument();
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!canReview || document.review_status !== "pending_review") return null;

  function submit(decision: "accepted" | "changes_requested") {
    const normalizedComment = comment.trim();
    if (decision === "changes_requested" && !normalizedComment) {
      setError("Explain what the employee needs to replace or correct.");
      return;
    }
    setError(null);
    review.mutate({
      documentId: document.id,
      request: {
        expected_document_version: document.version,
        decision,
        comment: normalizedComment || null,
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setComment("");
        setShowRequestForm(false);
      },
      onError: () => setError("The document review could not be saved. Refresh and try again."),
    });
  }

  return (
    <div className="mt-3 rounded-lg border border-blue-100 bg-white p-3">
      <p className="text-xs font-semibold text-gray-800">Review this document</p>
      {!showRequestForm ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={review.isPending}
            onClick={() => submit("accepted")}
            className="min-h-9 cursor-pointer rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {review.isPending ? "Saving…" : "Accept document"}
          </button>
          <button
            type="button"
            disabled={review.isPending}
            onClick={() => {
              setError(null);
              setShowRequestForm(true);
            }}
            className="min-h-9 cursor-pointer rounded-md border border-amber-300 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Request replacement
          </button>
        </div>
      ) : (
        <form className="mt-2 space-y-2" onSubmit={(event) => {
          event.preventDefault();
          submit("changes_requested");
        }}>
          <label className="block">
            <span className="mb-1 block text-xs text-gray-700">What should the employee change?</span>
            <textarea
              required
              maxLength={2000}
              rows={3}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
              placeholder="For example, upload a clearer copy with all pages visible."
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={review.isPending || !comment.trim()}
              className="min-h-9 cursor-pointer rounded-md bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {review.isPending ? "Sending…" : "Send replacement request"}
            </button>
            <button
              type="button"
              disabled={review.isPending}
              onClick={() => {
                setShowRequestForm(false);
                setComment("");
                setError(null);
              }}
              className="min-h-9 cursor-pointer rounded-md border border-gray-300 px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && <p className="mt-2 text-xs text-red-800" role="alert">{error}</p>}
    </div>
  );
}

export function DocumentAccessButton({
  document,
  mode,
}: {
  document: OnboardingTaskDocumentResponse;
  mode: "preview" | "download";
}) {
  const preview = useOnboardingTaskDocumentPreview();
  const download = useOnboardingTaskDocumentDownload();
  const [error, setError] = useState<string | null>(null);
  const isPending = preview.isPending || download.isPending;

  async function openDocument() {
    setError(null);
    const newWindow = window.open("about:blank", "_blank");
    if (newWindow) newWindow.opener = null;
    try {
      const authorization = mode === "preview"
        ? await preview.mutateAsync(document.id)
        : await download.mutateAsync(document.id);
      if (newWindow) {
        newWindow.location.href = authorization.url;
      } else {
        window.location.assign(authorization.url);
      }
    } catch {
      newWindow?.close();
      setError("The file could not be opened. Please try again.");
    }
  }

  return (
    <span className="inline-flex flex-col items-start">
      <button
        type="button"
        disabled={isPending}
        onClick={() => void openDocument()}
        className="min-h-8 cursor-pointer rounded-md border border-gray-300 bg-white px-2.5 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isPending ? "Opening…" : mode === "preview" ? "Preview" : "Download"}
      </button>
      {error && <span className="mt-1 text-xs text-red-800" role="alert">{error}</span>}
    </span>
  );
}

export function OnboardingTaskDocumentList({
  documents,
}: {
  documents: OnboardingTaskDocumentResponse[];
}) {
  const { data: session } = useSession();
  const canReview = session?.roles?.some((role) =>
    role === "tenant_admin" || role === "people_operations",
  ) ?? false;
  if (documents.length === 0) return null;

  return (
    <section className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3" aria-label="Documents submitted for this onboarding task">
      <h4 className="text-sm font-semibold text-gray-900">Employee-uploaded documents</h4>
      <ul className="mt-2 divide-y divide-gray-200">
        {documents.map((document) => (
          <li key={document.id} className="flex flex-col gap-2 py-3 first:pt-1 last:pb-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="break-all text-sm font-medium text-gray-800">{document.original_filename}</p>
              <p className={`mt-0.5 text-xs ${document.status === "available" ? "text-emerald-800" : document.status === "quarantined" || document.status === "rejected" ? "text-red-800" : "text-gray-600"}`}>
                {documentStatusLabel(document.status)} · {fileSizeLabel(document.expected_byte_size)}
              </p>
              {document.status === "available" && document.review_status !== "not_required" && (
                <p className="mt-1 text-xs font-medium text-blue-800">{reviewStatusLabel(document.review_status)}</p>
              )}
              {document.review_comment && (
                <p className="mt-2 whitespace-pre-wrap rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-950">
                  <span className="font-semibold">People Operations feedback: </span>
                  {document.review_comment}
                </p>
              )}
              {document.reviewed_at && (
                <p className="mt-1 text-xs text-gray-500">
                  Reviewed {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(document.reviewed_at))}
                </p>
              )}
            </div>
            {document.status === "available" && (
              <div className="flex shrink-0 gap-2">
                {document.declared_content_type === "application/pdf" && (
                  <DocumentAccessButton document={document} mode="preview" />
                )}
                <DocumentAccessButton document={document} mode="download" />
              </div>
            )}
            <DocumentReviewControls document={document} canReview={canReview} />
          </li>
        ))}
      </ul>
    </section>
  );
}
