"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { useApplication } from "@/lib/api/hooks/applications";
import { useCandidate } from "@/lib/api/hooks/candidates";
import {
  useCandidateDocumentDownload,
  useCandidateDocumentPreview,
  useCandidateDocuments,
} from "@/lib/api/hooks/documents";
import { useRequisition } from "@/lib/api/hooks/requisitions";
import type { ApplicationStatus } from "@/types/api/applications";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "New",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-1 wrap-break-word text-sm text-gray-900">{value || "Not provided"}</dd>
    </div>
  );
}

function formatFileSize(size: number): string {
  return size < 1024 * 1024
    ? `${Math.max(1, Math.round(size / 1024))} KB`
    : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function documentStatusLabel(status: string): string {
  switch (status) {
    case "available": return "Security scan complete · Ready to preview or download";
    case "pending_upload": return "Upload pending";
    case "uploaded":
    case "scanning": return "Security scan in progress";
    case "quarantined": return "Blocked by security scan";
    case "rejected": return "Could not be verified";
    default: return status.replaceAll("_", " ");
  }
}

export default function ApplicationDetailsPage() {
  const [previewPopupBlocked, setPreviewPopupBlocked] = useState(false);
  const { status: sessionStatus } = useSession();
  const { id } = useParams<{ id: string }>();
  const applicationQuery = useApplication(id);
  const application = applicationQuery.data;
  const candidateQuery = useCandidate(application?.candidate_id ?? "");
  const documentsQuery = useCandidateDocuments(application?.candidate_id ?? "");
  const downloadMutation = useCandidateDocumentDownload();
  const previewMutation = useCandidateDocumentPreview();
  const requisitionQuery = useRequisition(application?.requisition_id ?? "");
  const candidate = candidateQuery.data;
  const requisition = requisitionQuery.data;
  const isLoading = sessionStatus !== "authenticated" || applicationQuery.isLoading;
  const error = applicationQuery.isError
    ? "We couldn’t load this application. It may have been removed or you may not have access."
    : null;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <Link href="/dashboard/applications" className="w-fit text-sm font-medium text-gray-600 hover:text-sr-text-blue">
        ← Back to applications
      </Link>

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading application…
        </div>
      ) : error || !application ? (
        <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-8">
          <h1 className="text-lg font-semibold text-red-900">Application unavailable</h1>
          <p className="mt-2 text-sm text-red-800">{error ?? "This application could not be found."}</p>
          <Button asChild variant="outline" className="mt-5">
            <Link href="/dashboard/applications">Return to applications</Link>
          </Button>
        </section>
      ) : (
        <>
          <header className="flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-6 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Application</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">
                {candidate?.full_name ?? "Candidate unavailable"}
              </h1>
              <p className="mt-2 text-sm text-gray-600">
                {requisition?.title ?? "Job unavailable"}
                {requisition?.department ? ` · ${requisition.department}` : ""}
              </p>
            </div>
            <span className="w-fit rounded-full bg-sr-mint/60 px-3 py-1 text-sm font-semibold text-sr-text-blue">
              {STATUS_LABELS[application.status]}
            </span>
          </header>

          <div className="grid gap-6 lg:grid-cols-2">
            <section aria-labelledby="candidate-profile-heading" className="rounded-xl border border-gray-200 bg-white p-6">
              <h2 id="candidate-profile-heading" className="text-base font-semibold text-sr-text-blue">Candidate profile</h2>
              {candidate ? (
                <dl className="mt-5 grid gap-x-6 gap-y-5 sm:grid-cols-2">
                  <Detail label="Full name" value={candidate.full_name} />
                  <Detail label="Email" value={candidate.email} />
                  <Detail label="Phone" value={candidate.phone} />
                  <Detail label="Location" value={candidate.location} />
                  <Detail label="Source" value={candidate.source.replaceAll("_", " ")} />
                </dl>
              ) : (
                <p className="mt-3 text-sm text-gray-600">The candidate profile is unavailable or has been removed.</p>
              )}
            </section>

            <section aria-labelledby="application-info-heading" className="rounded-xl border border-gray-200 bg-white p-6">
              <h2 id="application-info-heading" className="text-base font-semibold text-sr-text-blue">Application details</h2>
              <dl className="mt-5 grid gap-x-6 gap-y-5 sm:grid-cols-2">
                <Detail label="Current stage" value={STATUS_LABELS[application.status]} />
                <Detail label="Applied" value={formatDate(application.applied_at)} />
                <Detail label="Last updated" value={formatDate(application.updated_at)} />
                <Detail label="Job status" value={requisition?.status.replaceAll("_", " ")} />
              </dl>
            </section>
          </div>

          <section aria-labelledby="application-documents-heading" className="rounded-xl border border-gray-200 bg-white p-6">
            <h2 id="application-documents-heading" className="text-base font-semibold text-sr-text-blue">Resume and documents</h2>
            {documentsQuery.isLoading ? (
              <p className="mt-3 text-sm text-gray-500" aria-live="polite">Loading candidate documents…</p>
            ) : documentsQuery.isError ? (
              <div role="alert" className="mt-3">
                <p className="text-sm text-red-800">We couldn’t load documents for this candidate.</p>
                <Button className="mt-2" variant="outline" onClick={() => void documentsQuery.refetch()}>Try again</Button>
              </div>
            ) : !documentsQuery.data?.length ? (
              <p className="mt-3 text-sm text-gray-600">No resume or other documents have been uploaded with this application.</p>
            ) : (
              <ul className="mt-4 divide-y divide-gray-100">
                {documentsQuery.data.map((document) => (
                  <li key={document.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="break-all text-sm font-medium text-gray-900">{document.original_filename}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {formatFileSize(document.expected_byte_size)} · {documentStatusLabel(document.status)}
                      </p>
                      {document.status === "available" &&
                        document.declared_content_type !== "application/pdf" && (
                          <p className="mt-1 text-xs text-gray-500">
                            Preview is available for PDF files. Download this file to view it.
                          </p>
                        )}
                      {(document.status === "uploaded" || document.status === "scanning") && (
                        <div className="mt-3 flex items-center gap-2 text-xs text-gray-600" role="status">
                          <span
                            aria-hidden="true"
                            className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-200 border-t-sr-green"
                          />
                          Security scan in progress. This status updates automatically.
                        </div>
                      )}
                    </div>
                    {document.status === "available" && (
                      <div className="flex shrink-0 gap-2">
                        {document.declared_content_type === "application/pdf" && (
                          <Button
                            type="button"
                            variant="outline"
                            disabled={previewMutation.isPending}
                            onClick={async () => {
                              setPreviewPopupBlocked(false);
                              const previewWindow = window.open("about:blank", "_blank");
                              if (!previewWindow) {
                                setPreviewPopupBlocked(true);
                                return;
                              }
                              previewWindow.opener = null;
                              try {
                                const authorization = await previewMutation.mutateAsync(document.id);
                                previewWindow.location.replace(authorization.url);
                              } catch {
                                previewWindow.close();
                              }
                            }}
                          >
                            {previewMutation.isPending ? "Preparing…" : "Preview"}
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          disabled={downloadMutation.isPending}
                          onClick={async () => {
                            try {
                              const authorization = await downloadMutation.mutateAsync(document.id);
                              window.location.assign(authorization.url);
                            } catch {
                              // The mutation error is announced below without exposing storage details.
                            }
                          }}
                        >
                          {downloadMutation.isPending ? "Preparing…" : "Download"}
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {downloadMutation.isError && (
              <p role="alert" className="mt-3 text-sm text-red-800">We couldn’t prepare the document download. Please try again.</p>
            )}
            {(previewMutation.isError || previewPopupBlocked) && (
              <p role="alert" className="mt-3 text-sm text-red-800">
                {previewPopupBlocked
                  ? "Your browser blocked the preview window. Allow pop-ups for this site and try again."
                  : "We couldn’t prepare the document preview. Please try again."}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
