"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { listApplicationPipeline } from "@/lib/api/services/applications";
import { listRequisitions } from "@/lib/api/services/requisitions";
import type { ApplicationPipelineItem, ApplicationStatus, RequisitionResponse } from "@/types/api";

const STAGES: { status: ApplicationStatus; label: string }[] = [
  { status: "applied", label: "New" },
  { status: "screening", label: "Screening" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "hired", label: "Hired" },
  { status: "rejected", label: "Rejected" },
  { status: "withdrawn", label: "Withdrawn" },
];

function formatAppliedDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(value),
  );
}

export default function ApplicationsPage() {
  const { status: sessionStatus } = useSession();
  const [applications, setApplications] = useState<ApplicationPipelineItem[]>([]);
  const [requisitions, setRequisitions] = useState<RequisitionResponse[]>([]);
  const [selectedRequisition, setSelectedRequisition] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionStatus !== "authenticated") return;
    let isCurrent = true;

    void Promise.all([
      listApplicationPipeline({
        limit: 100,
        ...(selectedRequisition ? { requisition_id: selectedRequisition } : {}),
      }),
      listRequisitions({ limit: 100 }),
    ])
      .then(([applicationPage, requisitionPage]) => {
        if (!isCurrent) return;
        setApplications(applicationPage.items);
        setNextCursor(applicationPage.next_cursor ?? null);
        setRequisitions(requisitionPage.items);
        setError(null);
      })
      .catch(() => {
        if (isCurrent) setError("We couldn’t load applications from your workspace. Please try again.");
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [sessionStatus, selectedRequisition]);

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    setIsLoadingMore(true);
    try {
      const page = await listApplicationPipeline({
        limit: 100,
        cursor: nextCursor,
        ...(selectedRequisition ? { requisition_id: selectedRequisition } : {}),
      });
      setApplications((current) => [...current, ...page.items]);
      setNextCursor(page.next_cursor ?? null);
    } catch {
      setError("We couldn’t load more applications. Please try again.");
    } finally {
      setIsLoadingMore(false);
    }
  }, [nextCursor, selectedRequisition]);

  const visibleApplications = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return applications;
    return applications.filter((application) =>
      [application.candidate_name, application.candidate_email, application.requisition_title]
        .some((value) => value?.toLocaleLowerCase().includes(query)),
    );
  }, [applications, searchQuery]);

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Recruit</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">Applications</h1>
          <p className="mt-2 text-sm text-gray-600">Review candidates and track progress across your open roles.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="sr-only" htmlFor="application-job-filter">Filter applications by job</label>
          <select
            id="application-job-filter"
            value={selectedRequisition}
            onChange={(event) => {
              setIsLoading(true);
              setApplications([]);
              setNextCursor(null);
              setSelectedRequisition(event.target.value);
            }}
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          >
            <option value="">All jobs</option>
            {requisitions.map((requisition) => (
              <option key={requisition.id} value={requisition.id}>{requisition.title}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor="application-search">Search applications</label>
          <input
            id="application-search"
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search candidates"
            className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm outline-none placeholder:text-gray-400 focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </div>
      </header>

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 sm:flex-row sm:items-center sm:justify-between">
          <p>{error}</p>
          <Button variant="outline" onClick={() => window.location.reload()}>Try again</Button>
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading applications…
        </div>
      ) : error && applications.length === 0 ? null : applications.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-16 text-center">
          <h2 className="text-base font-semibold text-sr-text-blue">No applications yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-gray-600">
            Applications submitted for your published jobs will appear here. Create or publish a job to start building your pipeline.
          </p>
          <Button asChild className="mt-5" variant="outline"><Link href="/dashboard/jobs">View jobs</Link></Button>
        </div>
      ) : visibleApplications.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center text-sm text-gray-600">
          No applications match this search. Try another candidate name or email.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto pb-3">
            <div className="grid min-w-[1680px] grid-cols-7 gap-3">
              {STAGES.map((stage) => {
                const stageApplications = visibleApplications.filter((application) => application.status === stage.status);
                return (
                  <section key={stage.status} aria-label={`${stage.label} applications`} className="min-h-72 rounded-xl bg-gray-100/80 p-3">
                    <header className="mb-3 flex items-center justify-between px-1">
                      <h2 className="text-sm font-semibold text-sr-text-blue">{stage.label}</h2>
                      <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-gray-600">{stageApplications.length}</span>
                    </header>
                    <div className="flex flex-col gap-2">
                      {stageApplications.map((application) => (
                        <article key={application.id} className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
                          <h3 className="text-sm font-semibold text-sr-text-blue">{application.candidate_name}</h3>
                          {application.candidate_email && <p className="mt-1 break-all text-xs text-gray-500">{application.candidate_email}</p>}
                          <p className="mt-3 text-xs font-medium text-gray-700">{application.requisition_title}</p>
                          <p className="mt-1 text-xs text-gray-500">Applied {formatAppliedDate(application.applied_at)}</p>
                        </article>
                      ))}
                      {stageApplications.length === 0 && <p className="px-1 py-3 text-xs text-gray-500">No candidates</p>}
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
          {nextCursor && (
            <div className="flex justify-center">
              <Button variant="outline" disabled={isLoadingMore} onClick={() => void loadMore()}>
                {isLoadingMore ? "Loading…" : "Load more applications"}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
