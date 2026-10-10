"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  useBulkTransitionApplicationStage,
  useApplicationPipeline,
  useTransitionApplicationStage,
} from "@/lib/api/hooks/applications";
import { useRequisitions } from "@/lib/api/hooks/requisitions";
import type {
  ApplicationPipelineItem,
  ApplicationRejectionReason,
  ApplicationStatus,
} from "@/types/api";

const STAGES: { status: ApplicationStatus; label: string }[] = [
  { status: "applied", label: "New" },
  { status: "screening", label: "Screening" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "hired", label: "Hired" },
  { status: "rejected", label: "Rejected" },
  { status: "withdrawn", label: "Withdrawn" },
];

const ALLOWED_NEXT_STAGES: Partial<Record<ApplicationStatus, ApplicationStatus[]>> = {
  applied: ["screening", "rejected"],
  screening: ["interview", "rejected"],
  interview: ["offer", "rejected"],
  offer: ["hired", "rejected"],
};

const REJECTION_REASONS: { value: ApplicationRejectionReason; label: string }[] = [
  { value: "not_qualified", label: "Does not meet role requirements" },
  { value: "better_matched_candidate", label: "Another candidate is a stronger match" },
  { value: "failed_assessment", label: "Did not pass an assessment" },
  { value: "compensation_mismatch", label: "Compensation mismatch" },
  { value: "role_closed", label: "Role is closed" },
  { value: "other", label: "Other" },
];

const APPLICATION_CARD_HEIGHT = 164;
const VIRTUAL_LIST_OVERSCAN = 5;

function formatAppliedDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(value),
  );
}

function VirtualizedApplicationLane({
  applications,
  ariaLabel,
  renderApplication,
}: {
  applications: ApplicationPipelineItem[];
  ariaLabel: string;
  renderApplication: (application: ApplicationPipelineItem) => ReactNode;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(560);
  const firstVisibleIndex = Math.max(
    0,
    Math.floor(scrollTop / APPLICATION_CARD_HEIGHT) - VIRTUAL_LIST_OVERSCAN,
  );
  const visibleItemCount = Math.ceil(viewportHeight / APPLICATION_CARD_HEIGHT)
    + VIRTUAL_LIST_OVERSCAN * 2;
  const lastVisibleIndex = Math.min(applications.length, firstVisibleIndex + visibleItemCount);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height;
      if (height) setViewportHeight(height);
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={viewportRef}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      className="min-h-16 max-h-[70vh] overflow-y-auto"
      role="list"
      aria-label={ariaLabel}
    >
      {applications.length === 0 ? (
        <p role="listitem" className="px-1 py-3 text-xs text-gray-500">No candidates on this page</p>
      ) : (
        <div role="presentation" className="relative" style={{ height: applications.length * APPLICATION_CARD_HEIGHT }}>
          {applications.slice(firstVisibleIndex, lastVisibleIndex).map((application, offset) => {
            const index = firstVisibleIndex + offset;
            return (
              <div
                key={application.id}
                role="presentation"
                className="absolute left-0 right-0"
                style={{
                  height: APPLICATION_CARD_HEIGHT,
                  transform: `translateY(${index * APPLICATION_CARD_HEIGHT}px)`,
                }}
              >
                {renderApplication(application)}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ApplicationsPage() {
  const { status: sessionStatus } = useSession();
  const [selectedRequisition, setSelectedRequisition] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<ApplicationStatus | "">("");
  const [appliedAfter, setAppliedAfter] = useState("");
  const [appliedBefore, setAppliedBefore] = useState("");
  const [view, setView] = useState<"jobs" | "board" | "table">("jobs");
  const [pendingRejection, setPendingRejection] = useState<ApplicationPipelineItem | null>(null);
  const [pendingBulkRejection, setPendingBulkRejection] = useState(false);
  const [selectedApplicationIds, setSelectedApplicationIds] = useState<Set<string>>(() => new Set());
  const [bulkFeedback, setBulkFeedback] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState<ApplicationRejectionReason>("not_qualified");
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearchQuery(searchQuery.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [searchQuery]);
  const invalidDateRange = Boolean(appliedAfter && appliedBefore && appliedAfter > appliedBefore);
  const applicationsQuery = useApplicationPipeline({
    limit: 50,
    ...(debouncedSearchQuery ? { query: debouncedSearchQuery } : {}),
    ...(selectedRequisition ? { requisition_id: selectedRequisition } : {}),
    ...(selectedStatus ? { status: selectedStatus } : {}),
    ...(!invalidDateRange && appliedAfter ? { applied_after: `${appliedAfter}T00:00:00Z` } : {}),
    ...(!invalidDateRange && appliedBefore ? { applied_before: `${appliedBefore}T23:59:59.999999Z` } : {}),
  });
  const requisitionsQuery = useRequisitions({ limit: 100 });
  const transitionMutation = useTransitionApplicationStage();
  const bulkTransitionMutation = useBulkTransitionApplicationStage();
  const applications = useMemo(
    () => applicationsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [applicationsQuery.data],
  );
  const jobApplicationGroups = useMemo(() => {
    const groups = new Map<string, { title: string; applications: ApplicationPipelineItem[] }>();
    for (const application of applications) {
      const group = groups.get(application.requisition_id) ?? {
        title: application.requisition_title,
        applications: [],
      };
      group.applications.push(application);
      groups.set(application.requisition_id, group);
    }
    return Array.from(groups, ([requisitionId, group]) => {
      const stageCounts = group.applications.reduce<Record<ApplicationStatus, number>>(
        (counts, application) => {
          counts[application.status] += 1;
          return counts;
        },
        { applied: 0, screening: 0, interview: 0, offer: 0, hired: 0, rejected: 0, withdrawn: 0 },
      );
      return { requisitionId, ...group, stageCounts };
    })
      .sort((left, right) => left.title.localeCompare(right.title));
  }, [applications]);
  const requisitions = requisitionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const selectedApplications = applications.filter((application) => selectedApplicationIds.has(application.id));
  const bulkStageOptions = selectedApplications.length
    ? (ALLOWED_NEXT_STAGES[selectedApplications[0].status] ?? []).filter((targetStatus) =>
      selectedApplications.every((application) =>
        ALLOWED_NEXT_STAGES[application.status]?.includes(targetStatus),
      ),
    )
    : [];
  const allLoadedApplicationsSelected = applications.length > 0
    && applications.every((application) => selectedApplicationIds.has(application.id));
  const isLoading = sessionStatus !== "authenticated"
    || applicationsQuery.isLoading
    || requisitionsQuery.isLoading;
  const isTransitioning = transitionMutation.isPending || bulkTransitionMutation.isPending;
  const error = applicationsQuery.isError || requisitionsQuery.isError
    ? "We couldn’t load applications from your workspace. Please try again."
    : null;
  const transitionError = transitionMutation.isError
    ? "We couldn’t update this application. Reload the pipeline and try again."
    : null;

  function moveApplication(
    application: ApplicationPipelineItem,
    targetStatus: ApplicationStatus,
    reason?: ApplicationRejectionReason,
  ) {
    setSelectedApplicationIds((current) => {
      if (!current.has(application.id)) return current;
      const next = new Set(current);
      next.delete(application.id);
      return next;
    });
    transitionMutation.mutate({
      id: application.id,
      targetStatus,
      expectedVersion: application.version,
      rejectionReason: reason,
      idempotencyKey: crypto.randomUUID(),
    });
  }

  function clearPipelineSelection() {
    setSelectedApplicationIds(new Set());
    setBulkFeedback(null);
    setPendingBulkRejection(false);
    setPendingRejection(null);
  }

  function toggleApplicationSelection(applicationId: string, selected: boolean) {
    setSelectedApplicationIds((current) => {
      const next = new Set(current);
      if (selected) next.add(applicationId);
      else next.delete(applicationId);
      return next;
    });
    setBulkFeedback(null);
  }

  function toggleAllLoadedApplications(selected: boolean) {
    setSelectedApplicationIds((current) => {
      const next = new Set(current);
      for (const application of applications) {
        if (selected) next.add(application.id);
        else next.delete(application.id);
      }
      return next;
    });
    setBulkFeedback(null);
  }

  async function moveSelectedApplications(
    targetStatus: ApplicationStatus,
    reason?: ApplicationRejectionReason,
  ) {
    const applicationsToMove = selectedApplications;
    if (!applicationsToMove.length) return;

    try {
      const results = await bulkTransitionMutation.mutateAsync({
        targetStatus,
        rejectionReason: reason,
        transitions: applicationsToMove.map((application) => ({
          id: application.id,
          expectedVersion: application.version,
          idempotencyKey: crypto.randomUUID(),
        })),
      });
      const failedIds = results.filter((result) => !result.application).map((result) => result.id);
      const succeeded = results.length - failedIds.length;
      const targetLabel = STAGES.find((stage) => stage.status === targetStatus)?.label ?? targetStatus;
      setSelectedApplicationIds(new Set(failedIds));
      setBulkFeedback(failedIds.length
        ? `${succeeded} application${succeeded === 1 ? "" : "s"} moved to ${targetLabel}; ${failedIds.length} could not be updated. The failed applications remain selected.`
        : `${succeeded} application${succeeded === 1 ? "" : "s"} moved to ${targetLabel}.`);
    } catch {
      setBulkFeedback("We couldn’t complete the bulk update. Refresh the pipeline and try again.");
    }
  }

  function renderStageActions(application: ApplicationPipelineItem) {
    const nextStages = ALLOWED_NEXT_STAGES[application.status] ?? [];
    if (!nextStages.length) return null;
    return (
      <label className="block">
        <span className="sr-only">Move {application.candidate_name} to another stage</span>
        <select
          value=""
          disabled={isTransitioning}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
          onChange={(event) => {
            const targetStatus = event.target.value as ApplicationStatus;
            if (!targetStatus) return;
            if (targetStatus === "rejected") {
              setRejectionReason("not_qualified");
              setPendingRejection(application);
              return;
            }
            void moveApplication(application, targetStatus);
          }}
          className="h-9 w-full rounded-md border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:opacity-50"
        >
          <option value="">Move to…</option>
          {nextStages.map((targetStatus) => (
            <option key={targetStatus} value={targetStatus}>
              {targetStatus === "rejected"
                ? "Reject application"
                : `Move to ${STAGES.find((stage) => stage.status === targetStatus)?.label ?? targetStatus}`}
            </option>
          ))}
        </select>
      </label>
    );
  }

  const loadedStageCounts = applications.reduce<Record<ApplicationStatus, number>>(
    (counts, application) => {
      counts[application.status] += 1;
      return counts;
    },
    { applied: 0, screening: 0, interview: 0, offer: 0, hired: 0, rejected: 0, withdrawn: 0 },
  );
  const stageCounts = applicationsQuery.data?.pages[0]?.stage_counts ?? loadedStageCounts;
  const totalMatchingApplications = Object.values(stageCounts).reduce((total, count) => total + count, 0);
  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">Recruit</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">Applications</h1>
          <p className="mt-2 text-sm text-gray-600">Review candidates and track progress across your open roles.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
            Search
            <input id="application-search" type="search" value={searchQuery} onChange={(event) => { clearPipelineSelection(); setSearchQuery(event.target.value); }} placeholder="Candidate, email, or job" className="h-10 min-w-56 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none placeholder:text-gray-400 focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
            Job
            <select id="application-job-filter" value={selectedRequisition} onChange={(event) => { clearPipelineSelection(); setSelectedRequisition(event.target.value); }} className="h-10 min-w-44 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20">
              <option value="">All jobs</option>
              {requisitions.map((requisition) => <option key={requisition.id} value={requisition.id}>{requisition.title}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
            Stage
            <select value={selectedStatus} onChange={(event) => { clearPipelineSelection(); setSelectedStatus(event.target.value as ApplicationStatus | ""); }} className="h-10 min-w-36 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20">
              <option value="">All stages</option>
              {STAGES.map((stage) => <option key={stage.status} value={stage.status}>{stage.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
            Applied from
            <input type="date" value={appliedAfter} onChange={(event) => { clearPipelineSelection(); setAppliedAfter(event.target.value); }} className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700" />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
            Applied to
            <input type="date" value={appliedBefore} onChange={(event) => { clearPipelineSelection(); setAppliedBefore(event.target.value); }} className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700" />
          </label>
        </div>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-600" aria-live="polite">
          {invalidDateRange ? "The start date must be on or before the end date." : `${totalMatchingApplications} matching application${totalMatchingApplications === 1 ? "" : "s"}`}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex self-start rounded-lg border border-gray-200 bg-white p-1" role="group" aria-label="Applications layout">
            <button type="button" aria-pressed={view === "jobs"} onClick={() => setView("jobs")} className={`rounded-md px-3 py-1.5 text-sm ${view === "jobs" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>By job</button>
            <button type="button" aria-pressed={view === "board"} onClick={() => setView("board")} className={`rounded-md px-3 py-1.5 text-sm ${view === "board" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>Pipeline</button>
            <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")} className={`rounded-md px-3 py-1.5 text-sm ${view === "table" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>Table</button>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={allLoadedApplicationsSelected}
            disabled={applications.length === 0 || isTransitioning}
            onChange={(event) => toggleAllLoadedApplications(event.target.checked)}
            className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
            aria-label="Select all loaded applications"
          />
          Select all loaded ({applications.length})
        </label>
        {selectedApplications.length > 0 && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <span className="text-sm font-medium text-gray-700" aria-live="polite">
              {selectedApplications.length} selected
            </span>
            {bulkStageOptions.length > 0 ? (
              <label className="sr-only" htmlFor="bulk-application-stage">Move selected applications</label>
            ) : null}
            <select
              id="bulk-application-stage"
              value=""
              disabled={isTransitioning || bulkStageOptions.length === 0}
              onChange={(event) => {
                const targetStatus = event.target.value as ApplicationStatus;
                if (!targetStatus) return;
                if (targetStatus === "rejected") {
                  setPendingRejection(null);
                  setRejectionReason("not_qualified");
                  setPendingBulkRejection(true);
                  return;
                }
                void moveSelectedApplications(targetStatus);
              }}
              className="h-10 min-w-48 rounded-md border border-gray-200 bg-white px-3 text-sm text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="">Choose a stage…</option>
              {bulkStageOptions.map((targetStatus) => (
                <option key={targetStatus} value={targetStatus}>
                  {targetStatus === "rejected"
                    ? "Reject selected"
                    : `Move to ${STAGES.find((stage) => stage.status === targetStatus)?.label ?? targetStatus}`}
                </option>
              ))}
            </select>
            <Button variant="outline" disabled={isTransitioning} onClick={clearPipelineSelection}>
              Clear selection
            </Button>
          </div>
        )}
      </div>
      {bulkFeedback && (
        <p className="text-sm text-gray-700" role="status" aria-live="polite">{bulkFeedback}</p>
      )}

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 sm:flex-row sm:items-center sm:justify-between">
          <p>{error}</p>
          <Button
            variant="outline"
            onClick={() => void Promise.all([
              applicationsQuery.refetch(),
              requisitionsQuery.refetch(),
            ])}
          >Try again</Button>
        </div>
      )}

      {transitionError && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {transitionError}
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading applications…
        </div>
      ) : error && applications.length === 0 ? null : totalMatchingApplications === 0 && (debouncedSearchQuery || selectedRequisition || selectedStatus || appliedAfter || appliedBefore) ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center text-sm text-gray-600">
          No applications match these filters. Try changing the search or filter values.
        </div>
      ) : totalMatchingApplications === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-16 text-center">
          <h2 className="text-base font-semibold text-sr-text-blue">No applications yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-gray-600">
            Applications submitted for your published jobs will appear here. Create or publish a job to start building your pipeline.
          </p>
          <Button asChild className="mt-5" variant="outline"><Link href="/dashboard/jobs">View jobs</Link></Button>
        </div>
      ) : (
        <>
          {view === "jobs" && (
            <div className="space-y-3">
              {jobApplicationGroups.map((group) => (
                <details key={group.requisitionId} className="group rounded-xl border border-gray-200 bg-white shadow-sm">
                  <summary className="flex cursor-pointer list-none flex-col gap-3 p-4 hover:bg-gray-50 sm:flex-row sm:items-center sm:justify-between [&::-webkit-details-marker]:hidden">
                    <div className="flex min-w-0 items-start gap-3">
                      <span aria-hidden="true" className="mt-0.5 text-gray-400 transition group-open:rotate-90">›</span>
                      <div className="min-w-0">
                        <h2 className="truncate text-sm font-semibold text-sr-text-blue">{group.title}</h2>
                        <p className="mt-1 text-xs text-gray-500">{group.applications.length} applicants loaded</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 pl-6 sm:pl-0" aria-label="Applicant counts by stage">
                      {STAGES.filter((stage) => group.stageCounts[stage.status] > 0).map((stage) => (
                        <span key={stage.status} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">
                          {stage.label} {group.stageCounts[stage.status]}
                        </span>
                      ))}
                      <span className="ml-1 text-xs font-medium text-sr-green">View applicants</span>
                    </div>
                  </summary>
                  <div className="border-t border-gray-100">
                    <div className="space-y-2 px-3 pb-3 sm:hidden">
                      {group.applications.map((application) => (
                        <article key={application.id} className="rounded-lg border border-gray-200 p-3">
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={selectedApplicationIds.has(application.id)}
                              disabled={isTransitioning}
                              onChange={(event) => toggleApplicationSelection(application.id, event.target.checked)}
                              className="mt-1 size-4 shrink-0 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                              aria-label={`Select ${application.candidate_name}`}
                            />
                            <div className="min-w-0 flex-1">
                              <Link href={`/dashboard/applications/${application.id}`} className="block truncate text-sm font-semibold text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                              {application.candidate_email && <p className="mt-0.5 break-all text-xs text-gray-500">{application.candidate_email}</p>}
                              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                                <span className="rounded-full bg-gray-100 px-2.5 py-1">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span>
                                <span>Applied {formatAppliedDate(application.applied_at)}</span>
                              </div>
                              <div className="mt-3">{renderStageActions(application)}</div>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                    <div className="hidden overflow-x-auto sm:block">
                      <table className="w-full min-w-[760px] text-left text-sm">
                        <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                          <tr>
                            <th className="w-12 px-4 py-3">Select</th>
                            <th className="px-4 py-3">Candidate</th>
                            <th className="px-4 py-3">Applied</th>
                            <th className="px-4 py-3">Stage</th>
                            <th className="w-48 px-4 py-3">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {group.applications.map((application) => (
                            <tr key={application.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3">
                                <input
                                  type="checkbox"
                                  checked={selectedApplicationIds.has(application.id)}
                                  disabled={isTransitioning}
                                  onChange={(event) => toggleApplicationSelection(application.id, event.target.checked)}
                                  className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                                  aria-label={`Select ${application.candidate_name}`}
                                />
                              </td>
                              <td className="px-4 py-3">
                                <Link href={`/dashboard/applications/${application.id}`} className="font-medium text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                                {application.candidate_email && <p className="mt-0.5 text-xs text-gray-500">{application.candidate_email}</p>}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-gray-600">{formatAppliedDate(application.applied_at)}</td>
                              <td className="px-4 py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span></td>
                              <td className="px-4 py-3">{renderStageActions(application)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
          {view === "table" && (
            <>
              <div className="space-y-2 sm:hidden">
                {applications.map((application) => (
                  <article key={application.id} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={selectedApplicationIds.has(application.id)}
                        disabled={isTransitioning}
                        onChange={(event) => toggleApplicationSelection(application.id, event.target.checked)}
                        className="mt-1 size-4 shrink-0 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                        aria-label={`Select ${application.candidate_name}`}
                      />
                      <div className="min-w-0 flex-1">
                        <Link href={`/dashboard/applications/${application.id}`} className="block truncate text-sm font-semibold text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                        {application.candidate_email && <p className="mt-0.5 break-all text-xs text-gray-500">{application.candidate_email}</p>}
                        <p className="mt-2 break-words text-xs font-medium text-gray-700">{application.requisition_title}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                          <span className="rounded-full bg-gray-100 px-2.5 py-1">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span>
                          <span>Applied {formatAppliedDate(application.applied_at)}</span>
                        </div>
                        <div className="mt-3">{renderStageActions(application)}</div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              <div className="hidden overflow-x-auto rounded-xl border border-gray-200 bg-white sm:block">
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th className="w-12 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={allLoadedApplicationsSelected}
                        disabled={applications.length === 0 || isTransitioning}
                        onChange={(event) => toggleAllLoadedApplications(event.target.checked)}
                        className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                        aria-label="Select all loaded applications"
                      />
                    </th>
                    <th className="px-4 py-3">Candidate</th>
                    <th className="px-4 py-3">Job</th>
                    <th className="px-4 py-3">Applied</th>
                    <th className="px-4 py-3">Stage</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {applications.map((application) => (
                    <tr key={application.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedApplicationIds.has(application.id)}
                          disabled={isTransitioning}
                          onChange={(event) => toggleApplicationSelection(application.id, event.target.checked)}
                          className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                          aria-label={`Select ${application.candidate_name}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/dashboard/applications/${application.id}`} className="font-medium text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                        {application.candidate_email && <p className="mt-0.5 text-xs text-gray-500">{application.candidate_email}</p>}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{application.requisition_title}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-600">{formatAppliedDate(application.applied_at)}</td>
                      <td className="px-4 py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span></td>
                      <td className="w-44 px-4 py-3">{renderStageActions(application)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </>
          )}
          {view === "board" && (
            <>
            <p className="mb-2 text-xs text-gray-500 sm:hidden">Swipe sideways to move between hiring stages.</p>
            <div className="snap-x snap-mandatory overflow-x-auto pb-3">
              <div className="grid min-w-[1680px] grid-cols-7 gap-3">
                {STAGES.map((stage) => {
                  const stageApplications = applications.filter((application) => application.status === stage.status);
                  return (
                    <section key={stage.status} aria-label={`${stage.label} applications`} className="min-h-72 snap-start rounded-xl bg-gray-100/80 p-3">
                      <header className="mb-3 flex items-center justify-between px-1">
                        <h2 className="text-sm font-semibold text-sr-text-blue">{stage.label}</h2>
                        <span className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-gray-600" aria-label={`${stageCounts[stage.status]} total in ${stage.label}`}>{stageCounts[stage.status]}</span>
                      </header>
                      <VirtualizedApplicationLane
                        key={`${stage.status}-${stageApplications.map((application) => application.id).join(",")}`}
                        applications={stageApplications}
                        ariaLabel={`${stage.label} applications`}
                        renderApplication={(application) => (
                          <article
                            role="listitem"
                            className="relative mb-2 h-[156px] overflow-hidden rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-sr-green/50 hover:shadow has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-sr-green"
                          >
                            <Link
                              aria-label={`Open ${application.candidate_name} application for ${application.requisition_title}`}
                              href={`/dashboard/applications/${application.id}`}
                              className="absolute inset-0 z-0 rounded-lg focus-visible:outline-none"
                            />
                            <input
                              type="checkbox"
                              checked={selectedApplicationIds.has(application.id)}
                              disabled={isTransitioning}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => toggleApplicationSelection(application.id, event.target.checked)}
                              className="absolute right-3 top-3 z-20 size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                              aria-label={`Select ${application.candidate_name}`}
                            />
                            <div className="pointer-events-none relative z-10">
                              <h3 className="truncate pr-7 text-sm font-semibold text-sr-text-blue">{application.candidate_name}</h3>
                              {application.candidate_email && <p className="mt-1 truncate text-xs text-gray-500">{application.candidate_email}</p>}
                              <p className="mt-2 truncate text-xs font-medium text-gray-700">{application.requisition_title}</p>
                              <p className="mt-1 text-xs text-gray-500">Applied {formatAppliedDate(application.applied_at)}</p>
                              <div className="pointer-events-auto mt-2">{renderStageActions(application)}</div>
                            </div>
                          </article>
                        )}
                      />
                    </section>
                  );
                })}
              </div>
            </div>
            </>
          )}
          <p className="text-center text-xs text-gray-500">Showing {applications.length} of {totalMatchingApplications} matching applications</p>
          {applicationsQuery.hasNextPage && (
            <div className="flex justify-center">
              <Button
                variant="outline"
                disabled={applicationsQuery.isFetchingNextPage}
                onClick={() => void applicationsQuery.fetchNextPage()}
              >
                {applicationsQuery.isFetchingNextPage ? "Loading…" : "Load more applications"}
              </Button>
            </div>
          )}
        </>
      )}

      {(pendingRejection || pendingBulkRejection) && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/40 p-4" role="presentation">
          <section
            aria-labelledby="reject-application-heading"
            aria-modal="true"
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
            role="dialog"
          >
            <h2 id="reject-application-heading" className="text-lg font-semibold text-sr-text-blue">
              {pendingBulkRejection
                ? `Reject ${selectedApplications.length} selected applications?`
                : `Reject ${pendingRejection?.candidate_name ?? "this application"}?`}
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              Choose a reason for the decision. {pendingBulkRejection
                ? "This will move each selected application to Rejected."
                : "This will move the application to Rejected."}
            </p>
            <label className="mt-5 block text-sm font-medium text-gray-700" htmlFor="rejection-reason">
              Rejection reason
            </label>
            <select
              id="rejection-reason"
              value={rejectionReason}
              onChange={(event) => setRejectionReason(event.target.value as ApplicationRejectionReason)}
              className="mt-2 h-10 w-full rounded-md border border-gray-200 bg-white px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              {REJECTION_REASONS.map((reason) => (
                <option key={reason.value} value={reason.value}>{reason.label}</option>
              ))}
            </select>
            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                disabled={isTransitioning}
                onClick={() => { setPendingRejection(null); setPendingBulkRejection(false); }}
              >
                Cancel
              </Button>
              <Button
                disabled={isTransitioning}
                onClick={() => {
                  setPendingRejection(null);
                  if (pendingBulkRejection) {
                    setPendingBulkRejection(false);
                    void moveSelectedApplications("rejected", rejectionReason);
                    return;
                  }
                  const application = pendingRejection;
                  if (application) void moveApplication(application, "rejected", rejectionReason);
                }}
              >
                {isTransitioning ? "Rejecting…" : pendingBulkRejection ? "Reject selected" : "Confirm rejection"}
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
