"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  useBulkTransitionApplicationStage,
  useApplicationPipeline,
  useApplicationPipelineSummary,
  useTransitionApplicationStage,
} from "@/lib/api/hooks/applications";
import type { ApplicationFilterParams } from "@/lib/api/services/applications";
import { useRequisitions } from "@/lib/api/hooks/requisitions";
import { ALLOWED_NEXT_APPLICATION_STAGES, APPLICATION_REJECTION_REASONS } from "@/lib/applications/stages";
import type {
  ApplicationPipelineItem,
  ApplicationPipelineJobSummary,
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

const APPLICATION_CARD_HEIGHT = 224;
const VIRTUAL_LIST_OVERSCAN = 5;

function formatAppliedDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(value),
  );
}

function FollowUpIndicator({
  action,
  dueAt,
}: {
  action: string | null;
  dueAt: string | null;
}) {
  if (!action || !dueAt) {
    return <span className="text-xs text-gray-400">No follow-up</span>;
  }
  const dueDate = new Date(dueAt);
  const now = new Date();
  const isOverdue = dueDate < now;
  const isDueToday = dueDate.toDateString() === now.toDateString();
  const label = isOverdue ? "Overdue" : isDueToday ? "Due today" : "Due";
  const style = isOverdue
    ? "bg-red-100 text-red-800"
    : isDueToday
      ? "bg-amber-100 text-amber-900"
      : "bg-blue-50 text-blue-800";

  return (
    <span title={`${action} · ${label} ${formatAppliedDate(dueAt)}`} className={`inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${style}`}>
      <span className="shrink-0 font-semibold">{label} · {formatAppliedDate(dueAt)}</span>
      <span className="truncate">{action}</span>
    </span>
  );
}

function ScreeningProgressBadge({ progress }: { progress: ApplicationPipelineItem["screening_progress"] }) {
  const label = progress === "complete"
    ? "Complete"
    : progress === "in_progress"
      ? "In progress"
      : "Not started";
  const styles = progress === "complete"
    ? "bg-emerald-50 text-emerald-800"
    : progress === "in_progress"
      ? "bg-amber-50 text-amber-900"
      : "bg-gray-100 text-gray-700";

  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${styles}`}>Screening: {label}</span>;
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

function JobApplicationGroup({
  group,
  filters,
  selectedApplications,
  isTransitioning,
  onToggleSelection,
  renderStageActions,
}: {
  group: ApplicationPipelineJobSummary;
  filters: ApplicationFilterParams;
  selectedApplications: ReadonlyMap<string, ApplicationPipelineItem>;
  isTransitioning: boolean;
  onToggleSelection: (application: ApplicationPipelineItem, selected: boolean) => void;
  renderStageActions: (application: ApplicationPipelineItem) => ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const applicationsQuery = useApplicationPipeline({
    ...filters,
    requisition_id: group.requisition_id,
    limit: 50,
  }, expanded);
  const applications = useMemo(
    () => applicationsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [applicationsQuery.data],
  );
  const allLoadedSelected = applications.length > 0
    && applications.every((application) => selectedApplications.has(application.id));

  function toggleAllLoaded(selected: boolean) {
    for (const application of applications) onToggleSelection(application, selected);
  }

  return (
    <details
      className="group rounded-xl border border-gray-200 bg-white shadow-sm"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none flex-col gap-3 p-4 hover:bg-gray-50 sm:flex-row sm:items-center sm:justify-between [&::-webkit-details-marker]:hidden">
        <div className="flex min-w-0 items-start gap-3">
          <span aria-hidden="true" className="mt-0.5 text-gray-400 transition group-open:rotate-90">›</span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-sr-text-blue">{group.requisition_title}</h2>
            <p className="mt-1 text-xs text-gray-500">{group.total_count} application{group.total_count === 1 ? "" : "s"}</p>
            {group.follow_up_count > 0 && (
              <p className="mt-1 text-xs text-gray-600">
                {group.follow_up_count} follow-up{group.follow_up_count === 1 ? "" : "s"}
                {group.overdue_follow_up_count > 0 ? ` · ${group.overdue_follow_up_count} overdue` : ""}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 pl-6 sm:pl-0" aria-label="Applicant counts by stage">
          {STAGES.filter((stage) => group.stage_counts[stage.status] > 0).map((stage) => (
            <span key={stage.status} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">
              {stage.label} {group.stage_counts[stage.status]}
            </span>
          ))}
          <span className="ml-1 text-xs font-medium text-sr-green">View applications</span>
        </div>
      </summary>
      <div className="border-t border-gray-100 p-3">
        {applicationsQuery.isLoading ? (
          <p className="px-1 py-4 text-sm text-gray-500" role="status">Loading applications…</p>
        ) : applicationsQuery.isError ? (
          <div className="flex flex-col gap-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 sm:flex-row sm:items-center sm:justify-between" role="alert">
            <p>We couldn’t load applications for this job.</p>
            <Button variant="outline" onClick={() => void applicationsQuery.refetch()}>Try again</Button>
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={allLoadedSelected}
                  disabled={applications.length === 0 || isTransitioning}
                  onChange={(event) => toggleAllLoaded(event.target.checked)}
                  className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                  aria-label={`Select all ${applications.length} loaded applications for ${group.requisition_title}`}
                />
                Select loaded applications ({applications.length})
              </label>
              {applicationsQuery.hasNextPage && (
                <Button
                  variant="outline"
                  disabled={applicationsQuery.isFetchingNextPage}
                  onClick={() => void applicationsQuery.fetchNextPage()}
                >
                  {applicationsQuery.isFetchingNextPage ? "Loading…" : "Load more for this job"}
                </Button>
              )}
            </div>
            <div className="space-y-2 xl:hidden">
              {applications.map((application) => (
                <article key={application.id} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selectedApplications.has(application.id)}
                      disabled={isTransitioning}
                      onChange={(event) => onToggleSelection(application, event.target.checked)}
                      className="mt-1 size-4 shrink-0 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                      aria-label={`Select ${application.candidate_name}`}
                    />
                    <div className="min-w-0 flex-1">
                      <Link href={`/dashboard/applications/${application.id}`} className="block truncate text-sm font-semibold text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                      {application.candidate_email && <p className="mt-0.5 break-all text-xs text-gray-500">{application.candidate_email}</p>}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                        <span className="rounded-full bg-gray-100 px-2.5 py-1">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span>
                        <ScreeningProgressBadge progress={application.screening_progress} />
                        <span>Applied {formatAppliedDate(application.applied_at)}</span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500">Owner: {application.assigned_to_display_name ?? "Unassigned"}</p>
                      <div className="mt-2"><FollowUpIndicator action={application.follow_up_action} dueAt={application.follow_up_due_at} /></div>
                      <div className="mt-3">{renderStageActions(application)}</div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <div className="hidden overflow-x-auto xl:block">
              <table className="w-full min-w-190 text-left text-sm">
                <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr><th className="w-12 px-4 py-3">Select</th><th className="px-4 py-3">Candidate</th><th className="px-4 py-3">Owner</th><th className="px-4 py-3">Next action</th><th className="px-4 py-3">Applied</th><th className="px-4 py-3">Stage</th><th className="px-4 py-3">Screening</th><th className="w-48 px-4 py-3">Actions</th></tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {applications.map((application) => (
                    <tr key={application.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedApplications.has(application.id)}
                          disabled={isTransitioning}
                          onChange={(event) => onToggleSelection(application, event.target.checked)}
                          className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                          aria-label={`Select ${application.candidate_name}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/dashboard/applications/${application.id}`} className="font-medium text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                        {application.candidate_email && <p className="mt-0.5 text-xs text-gray-500">{application.candidate_email}</p>}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{application.assigned_to_display_name ?? "Unassigned"}</td>
                      <td className="px-4 py-3"><FollowUpIndicator action={application.follow_up_action} dueAt={application.follow_up_due_at} /></td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-600">{formatAppliedDate(application.applied_at)}</td>
                      <td className="px-4 py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span></td>
                      <td className="px-4 py-3"><ScreeningProgressBadge progress={application.screening_progress} /></td>
                      <td className="px-4 py-3">{renderStageActions(application)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </details>
  );
}

export default function ApplicationsPage() {
  const { status: sessionStatus } = useSession();
  const [selectedRequisition, setSelectedRequisition] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<ApplicationStatus | "">("");
  const [myApplicationsOnly, setMyApplicationsOnly] = useState(false);
  const [followUpDueOnly, setFollowUpDueOnly] = useState(false);
  const [needsScreeningOnly, setNeedsScreeningOnly] = useState(false);
  const [appliedAfter, setAppliedAfter] = useState("");
  const [appliedBefore, setAppliedBefore] = useState("");
  const [view, setView] = useState<"jobs" | "board" | "table">("jobs");
  const [pendingRejection, setPendingRejection] = useState<ApplicationPipelineItem | null>(null);
  const [pendingBulkRejection, setPendingBulkRejection] = useState(false);
  const [selectedApplicationById, setSelectedApplicationById] = useState<Map<string, ApplicationPipelineItem>>(
    () => new Map(),
  );
  const [bulkFeedback, setBulkFeedback] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState<ApplicationRejectionReason>("not_qualified");
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearchQuery(searchQuery.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [searchQuery]);
  const invalidDateRange = Boolean(appliedAfter && appliedBefore && appliedAfter > appliedBefore);
  const applicationFilters: ApplicationFilterParams = {
    ...(debouncedSearchQuery ? { query: debouncedSearchQuery } : {}),
    ...(selectedRequisition ? { requisition_id: selectedRequisition } : {}),
    ...(selectedStatus ? { status: selectedStatus } : {}),
    ...(myApplicationsOnly ? { mine: true } : {}),
    ...(followUpDueOnly ? { follow_up: "due" as const } : {}),
    ...(needsScreeningOnly ? { needs_screening: true } : {}),
    ...(!invalidDateRange && appliedAfter ? { applied_after: `${appliedAfter}T00:00:00Z` } : {}),
    ...(!invalidDateRange && appliedBefore ? { applied_before: `${appliedBefore}T23:59:59.999999Z` } : {}),
  };
  const applicationsQuery = useApplicationPipeline({ limit: 50, ...applicationFilters }, view !== "jobs");
  const summaryQuery = useApplicationPipelineSummary(applicationFilters, view === "jobs");
  const requisitionsQuery = useRequisitions({ limit: 100 });
  const transitionMutation = useTransitionApplicationStage();
  const bulkTransitionMutation = useBulkTransitionApplicationStage();
  const applications = useMemo(
    () => applicationsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [applicationsQuery.data],
  );
  const jobApplicationGroups = summaryQuery.data?.jobs ?? [];
  const requisitions = requisitionsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const selectedApplications = Array.from(selectedApplicationById.values());
  const selectedApplicationIds = new Set(selectedApplicationById.keys());
  const bulkStageOptions = selectedApplications.length
    ? (ALLOWED_NEXT_APPLICATION_STAGES[selectedApplications[0].status] ?? []).filter((targetStatus) =>
      selectedApplications.every((application) =>
        ALLOWED_NEXT_APPLICATION_STAGES[application.status]?.includes(targetStatus),
      ),
    )
    : [];
  const allLoadedApplicationsSelected = view !== "jobs" && applications.length > 0
    && applications.every((application) => selectedApplicationIds.has(application.id));
  const isLoading = sessionStatus !== "authenticated"
    || (view === "jobs" ? summaryQuery.isLoading : applicationsQuery.isLoading)
    || requisitionsQuery.isLoading;
  const isTransitioning = transitionMutation.isPending || bulkTransitionMutation.isPending;
  const error = (view === "jobs" ? summaryQuery.isError : applicationsQuery.isError) || requisitionsQuery.isError
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
    setSelectedApplicationById((current) => {
      if (!current.has(application.id)) return current;
      const next = new Map(current);
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
    setSelectedApplicationById(new Map());
    setBulkFeedback(null);
    setPendingBulkRejection(false);
    setPendingRejection(null);
  }

  function toggleApplicationSelection(application: ApplicationPipelineItem, selected: boolean) {
    setSelectedApplicationById((current) => {
      const next = new Map(current);
      if (selected) next.set(application.id, application);
      else next.delete(application.id);
      return next;
    });
    setBulkFeedback(null);
  }

  function toggleAllLoadedApplications(selected: boolean) {
    setSelectedApplicationById((current) => {
      const next = new Map(current);
      for (const application of applications) {
        if (selected) next.set(application.id, application);
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
      const failedApplications = new Map<string, ApplicationPipelineItem>();
      for (const id of failedIds) {
        const application = selectedApplicationById.get(id);
        if (application) failedApplications.set(id, application);
      }
      setSelectedApplicationById(failedApplications);
      setBulkFeedback(failedIds.length
        ? `${succeeded} application${succeeded === 1 ? "" : "s"} moved to ${targetLabel}; ${failedIds.length} could not be updated. The failed applications remain selected.`
        : `${succeeded} application${succeeded === 1 ? "" : "s"} moved to ${targetLabel}.`);
    } catch {
      setBulkFeedback("We couldn’t complete the bulk update. Refresh the pipeline and try again.");
    }
  }

  function renderStageActions(application: ApplicationPipelineItem) {
    const nextStages = ALLOWED_NEXT_APPLICATION_STAGES[application.status] ?? [];
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
  const stageCounts = view === "jobs"
    ? summaryQuery.data?.stage_counts ?? loadedStageCounts
    : applicationsQuery.data?.pages[0]?.stage_counts ?? loadedStageCounts;
  const totalMatchingApplications = view === "jobs"
    ? summaryQuery.data?.total_count ?? 0
    : Object.values(stageCounts).reduce((total, count) => total + count, 0);
  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
      <header className="flex flex-col gap-4">
        <div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-sr-text-blue">Applications</h1>
          <p className="mt-2 text-sm text-gray-600">Review candidates and track progress across your open roles.</p>
        </div>
        <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Search
            <input id="application-search" type="search" value={searchQuery} onChange={(event) => { clearPipelineSelection(); setSearchQuery(event.target.value); }} placeholder="Candidate, email, or job" className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none placeholder:text-gray-400 focus:border-sr-green focus:ring-2 focus:ring-sr-green/20" />
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Job
            <select id="application-job-filter" value={selectedRequisition} onChange={(event) => { clearPipelineSelection(); setSelectedRequisition(event.target.value); }} className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20">
              <option value="">All jobs</option>
              {requisitions.map((requisition) => <option key={requisition.id} value={requisition.id}>{requisition.title}</option>)}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Stage
            <select value={selectedStatus} onChange={(event) => { clearPipelineSelection(); setSelectedStatus(event.target.value as ApplicationStatus | ""); }} className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20">
              <option value="">All stages</option>
              {STAGES.map((stage) => <option key={stage.status} value={stage.status}>{stage.label}</option>)}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Assignment
            <select
              value={myApplicationsOnly ? "mine" : "all"}
              onChange={(event) => {
                clearPipelineSelection();
                setMyApplicationsOnly(event.target.value === "mine");
              }}
              className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              <option value="all">All applications</option>
              <option value="mine">My applications</option>
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Follow-up
            <select
              value={followUpDueOnly ? "due" : "all"}
              onChange={(event) => {
                clearPipelineSelection();
                setFollowUpDueOnly(event.target.value === "due");
              }}
              className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              <option value="all">All follow-ups</option>
              <option value="due">Due or overdue</option>
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Screening
            <select
              value={needsScreeningOnly ? "needs-screening" : "all"}
              onChange={(event) => {
                clearPipelineSelection();
                setNeedsScreeningOnly(event.target.value === "needs-screening");
              }}
              className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            >
              <option value="all">All statuses</option>
              <option value="needs-screening">Needs screening</option>
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Applied from
            <input type="date" value={appliedAfter} onChange={(event) => { clearPipelineSelection(); setAppliedAfter(event.target.value); }} className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700" />
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-gray-600">
            Applied to
            <input type="date" value={appliedBefore} onChange={(event) => { clearPipelineSelection(); setAppliedBefore(event.target.value); }} className="h-10 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal text-gray-700" />
          </label>
        </div>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {invalidDateRange && (
          <p className="text-sm text-red-700" role="alert">The start date must be on or before the end date.</p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex self-start rounded-lg border border-gray-200 bg-white p-1" role="group" aria-label="Applications layout">
            <button type="button" aria-pressed={view === "jobs"} onClick={() => setView("jobs")} className={`rounded-md px-3 py-1.5 text-sm ${view === "jobs" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>By job</button>
            <button type="button" aria-pressed={view === "board"} onClick={() => setView("board")} className={`rounded-md px-3 py-1.5 text-sm ${view === "board" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>Pipeline</button>
            <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")} className={`rounded-md px-3 py-1.5 text-sm ${view === "table" ? "bg-sr-text-blue text-white" : "text-gray-700 hover:bg-gray-100"}`}>Table</button>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
        {view === "jobs" ? (
          <p className="text-sm text-gray-600">Expand a job to select its loaded applications for bulk actions.</p>
        ) : (
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
        )}
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
              view === "jobs" ? summaryQuery.refetch() : applicationsQuery.refetch(),
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
      ) : error && applications.length === 0 ? null : totalMatchingApplications === 0 && (debouncedSearchQuery || selectedRequisition || selectedStatus || appliedAfter || appliedBefore || myApplicationsOnly || followUpDueOnly || needsScreeningOnly) ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center text-sm text-gray-600">
          {needsScreeningOnly && !debouncedSearchQuery && !selectedRequisition && !selectedStatus && !appliedAfter && !appliedBefore && !myApplicationsOnly && !followUpDueOnly
            ? "All active applications have a screening assessment."
            : followUpDueOnly && !debouncedSearchQuery && !selectedRequisition && !selectedStatus && !appliedAfter && !appliedBefore && !myApplicationsOnly && !needsScreeningOnly
            ? "No follow-ups are due or overdue."
            : myApplicationsOnly && !debouncedSearchQuery && !selectedRequisition && !selectedStatus && !appliedAfter && !appliedBefore && !followUpDueOnly && !needsScreeningOnly
            ? "No applications are assigned to you yet. Ask a teammate to assign one to you."
            : "No applications match these filters. Try changing the search or filter values."}
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
                <JobApplicationGroup
                  key={group.requisition_id}
                  group={group}
                  filters={applicationFilters}
                  selectedApplications={selectedApplicationById}
                  isTransitioning={isTransitioning}
                  onToggleSelection={toggleApplicationSelection}
                  renderStageActions={renderStageActions}
                />
              ))}
            </div>
          )}
          {view === "table" && (
            <>
              <div className="space-y-2 xl:hidden">
                {applications.map((application) => (
                  <article key={application.id} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={selectedApplicationIds.has(application.id)}
                        disabled={isTransitioning}
                        onChange={(event) => toggleApplicationSelection(application, event.target.checked)}
                        className="mt-1 size-4 shrink-0 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                        aria-label={`Select ${application.candidate_name}`}
                      />
                      <div className="min-w-0 flex-1">
                        <Link href={`/dashboard/applications/${application.id}`} className="block truncate text-sm font-semibold text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                        {application.candidate_email && <p className="mt-0.5 break-all text-xs text-gray-500">{application.candidate_email}</p>}
                        <p className="mt-2 wrap-break-word text-xs font-medium text-gray-700">{application.requisition_title}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                          <span className="rounded-full bg-gray-100 px-2.5 py-1">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span>
                          <ScreeningProgressBadge progress={application.screening_progress} />
                          <span>Applied {formatAppliedDate(application.applied_at)}</span>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">Owner: {application.assigned_to_display_name ?? "Unassigned"}</p>
                        <div className="mt-2"><FollowUpIndicator action={application.follow_up_action} dueAt={application.follow_up_due_at} /></div>
                        <div className="mt-3">{renderStageActions(application)}</div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              <div className="hidden overflow-x-auto rounded-xl border border-gray-200 bg-white xl:block">
              <table className="w-full min-w-195 text-left text-sm">
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
                    <th className="px-4 py-3">Owner</th>
                    <th className="px-4 py-3">Next action</th>
                    <th className="px-4 py-3">Applied</th>
                    <th className="px-4 py-3">Stage</th>
                    <th className="px-4 py-3">Screening</th>
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
                          onChange={(event) => toggleApplicationSelection(application, event.target.checked)}
                          className="size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                          aria-label={`Select ${application.candidate_name}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/dashboard/applications/${application.id}`} className="font-medium text-sr-text-blue hover:text-sr-green">{application.candidate_name}</Link>
                        {application.candidate_email && <p className="mt-0.5 text-xs text-gray-500">{application.candidate_email}</p>}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{application.requisition_title}</td>
                      <td className="px-4 py-3 text-gray-700">{application.assigned_to_display_name ?? "Unassigned"}</td>
                      <td className="px-4 py-3"><FollowUpIndicator action={application.follow_up_action} dueAt={application.follow_up_due_at} /></td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-600">{formatAppliedDate(application.applied_at)}</td>
                      <td className="px-4 py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">{STAGES.find((stage) => stage.status === application.status)?.label ?? application.status}</span></td>
                      <td className="px-4 py-3"><ScreeningProgressBadge progress={application.screening_progress} /></td>
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
            <p className="mb-2 text-xs text-gray-500 2xl:hidden">Swipe or scroll sideways to move between hiring stages.</p>
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
                className="relative mb-2 h-56 overflow-hidden rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-sr-green/50 hover:shadow has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-sr-green"
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
                              onChange={(event) => toggleApplicationSelection(application, event.target.checked)}
                              className="absolute right-3 top-3 z-20 size-4 cursor-pointer accent-sr-green disabled:cursor-not-allowed"
                              aria-label={`Select ${application.candidate_name}`}
                            />
                            <div className="pointer-events-none relative z-10">
                              <h3 className="truncate pr-7 text-sm font-semibold text-sr-text-blue">{application.candidate_name}</h3>
                              {application.candidate_email && <p className="mt-1 truncate text-xs text-gray-500">{application.candidate_email}</p>}
                              <p className="mt-2 truncate text-xs font-medium text-gray-700">{application.requisition_title}</p>
                              <div className="mt-1"><ScreeningProgressBadge progress={application.screening_progress} /></div>
                              <p className="mt-1 text-xs text-gray-500">Applied {formatAppliedDate(application.applied_at)}</p>
                              <p className="mt-1 truncate text-xs text-gray-500">Owner: {application.assigned_to_display_name ?? "Unassigned"}</p>
                              <div className="mt-1 truncate"><FollowUpIndicator action={application.follow_up_action} dueAt={application.follow_up_due_at} /></div>
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
          {view !== "jobs" && (
            <p className="text-center text-xs text-gray-500">Showing {applications.length} loaded applications</p>
          )}
          {view !== "jobs" && applicationsQuery.hasNextPage && (
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
              {APPLICATION_REJECTION_REASONS.map((reason) => (
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
