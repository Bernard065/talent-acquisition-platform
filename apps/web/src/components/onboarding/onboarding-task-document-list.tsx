"use client";

import { useState } from "react";
import {
  useOnboardingTaskDocumentDownload,
  useOnboardingTaskDocumentPreview,
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

function DocumentAccessButton({
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
            </div>
            {document.status === "available" && (
              <div className="flex shrink-0 gap-2">
                {document.declared_content_type === "application/pdf" && (
                  <DocumentAccessButton document={document} mode="preview" />
                )}
                <DocumentAccessButton document={document} mode="download" />
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
