"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { getApplication } from "@/lib/api/services/applications";
import { getCandidate } from "@/lib/api/services/candidates";
import { getRequisition } from "@/lib/api/services/requisitions";
import type { ApplicationResponse, CandidateResponse, RequisitionResponse } from "@/types/api";

const STATUS_LABELS: Record<ApplicationResponse["status"], string> = {
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
      <dd className="mt-1 break-words text-sm text-gray-900">{value || "Not provided"}</dd>
    </div>
  );
}

export default function ApplicationDetailsPage() {
  const { status: sessionStatus } = useSession();
  const { id } = useParams<{ id: string }>();
  const [application, setApplication] = useState<ApplicationResponse | null>(null);
  const [candidate, setCandidate] = useState<CandidateResponse | null>(null);
  const [requisition, setRequisition] = useState<RequisitionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionStatus !== "authenticated" || !id) return;
    let isCurrent = true;

    void getApplication(id)
      .then(async (applicationResult) => {
        const [candidateResult, requisitionResult] = await Promise.all([
          getCandidate(applicationResult.candidate_id).catch(() => null),
          getRequisition(applicationResult.requisition_id).catch(() => null),
        ]);
        if (!isCurrent) return;
        setApplication(applicationResult);
        setCandidate(candidateResult);
        setRequisition(requisitionResult);
      })
      .catch(() => {
        if (isCurrent) setError("We couldn’t load this application. It may have been removed or you may not have access.");
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [sessionStatus, id]);

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
        </>
      )}
    </div>
  );
}
