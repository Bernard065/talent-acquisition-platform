"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { ApplicationDebriefSection } from "@/components/applications/application-debrief-section";
import { ApplicationScreeningAssessmentSection } from "@/components/applications/application-screening-assessment-section";
import { ApplicationStageControl } from "@/components/applications/application-stage-control";
import { ApplicationOfferSection } from "@/components/applications/application-offer-section";
import { ApplicationInterviewFeedbackSection } from "@/components/applications/application-interview-feedback-section";
import {
  useApplication,
  useApplicationActivity,
  useAssignApplication,
  useApplicationFollowUps,
  useCompleteApplicationFollowUp,
  useCreateApplicationFollowUp,
  useUpdateApplicationFollowUp,
} from "@/lib/api/hooks/applications";
import { useCandidate } from "@/lib/api/hooks/candidates";
import {
  useCandidateDocumentDownload,
  useCandidateDocumentPreview,
  useCandidateDocuments,
} from "@/lib/api/hooks/documents";
import { useRequisition } from "@/lib/api/hooks/requisitions";
import { useTeamInterviewers, useTeamMembers } from "@/lib/api/hooks/team";
import { useInterviews, useScheduleInterview } from "@/lib/api/hooks/interviews";
import type {
  ApplicationRejectionReason,
  ApplicationStatus,
  InterviewFormat,
} from "@/types/api";

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "New",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const REJECTION_REASON_LABELS: Record<ApplicationRejectionReason, string> = {
  not_qualified: "Does not meet role requirements",
  better_matched_candidate: "Another candidate was a stronger match",
  failed_assessment: "Did not meet assessment criteria",
  compensation_mismatch: "Compensation expectations did not align",
  role_closed: "Role is no longer open",
  other: "Other",
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

function toDateTimeLocalValue(value: string | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function followUpTiming(dueAt: string): { label: string; className: string } {
  const dueDate = new Date(dueAt);
  const now = new Date();
  if (dueDate < now) {
    return { label: "Overdue", className: "bg-red-100 text-red-800" };
  }
  if (dueDate.toDateString() === now.toDateString()) {
    return { label: "Due today", className: "bg-amber-100 text-amber-900" };
  }
  return { label: "Upcoming", className: "bg-blue-50 text-blue-800" };
}

function ApplicationFollowUpsSection({ applicationId }: { applicationId: string }) {
  const followUpsQuery = useApplicationFollowUps(applicationId);
  const activeFollowUp = followUpsQuery.data?.items.find(
    (item) => item.id === followUpsQuery.data?.active_follow_up_id,
  );

  return (
    <section aria-labelledby="application-follow-ups-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-follow-ups-heading" className="text-base font-semibold text-sr-text-blue">Next action</h2>
        <p className="mt-1 text-sm text-gray-600">Record the next candidate touchpoint and when it should happen.</p>
      </div>
      {followUpsQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading follow-ups…</p>
      ) : followUpsQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">We couldn’t load follow-ups for this application.</p>
          <Button type="button" variant="outline" onClick={() => void followUpsQuery.refetch()}>Try again</Button>
        </div>
      ) : (
        <>
          <ApplicationFollowUpEditor
            key={activeFollowUp?.id ?? "new-follow-up"}
            applicationId={applicationId}
            activeFollowUp={activeFollowUp}
          />
          <div className="mt-6 border-t border-gray-100 pt-5">
            <h3 className="text-sm font-semibold text-gray-800">Follow-up history</h3>
            {!followUpsQuery.data?.items.length ? (
              <p className="mt-3 text-sm text-gray-600">No follow-ups have been recorded.</p>
            ) : (
              <ol className="mt-3 space-y-3">
                {followUpsQuery.data.items.map((item) => {
                  const timing = followUpTiming(item.due_at);
                  return (
                    <li key={item.id} className="rounded-lg border border-gray-100 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="min-w-0 flex-1 text-sm font-medium text-gray-900">{item.action}</p>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${item.completed_at ? "bg-green-100 text-green-800" : timing.className}`}>
                          {item.completed_at ? "Completed" : timing.label}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-gray-600">
                        Due {formatDate(item.due_at)} · Added {formatDate(item.created_at)}
                        {item.completed_at ? ` · Completed ${formatDate(item.completed_at)}` : ""}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function ApplicationFollowUpEditor({
  applicationId,
  activeFollowUp,
}: {
  applicationId: string;
  activeFollowUp?: { id: string; action: string; due_at: string; version: number };
}) {
  const [action, setAction] = useState(activeFollowUp?.action ?? "");
  const [dueAt, setDueAt] = useState(toDateTimeLocalValue(activeFollowUp?.due_at));
  const createMutation = useCreateApplicationFollowUp();
  const updateMutation = useUpdateApplicationFollowUp();
  const completeMutation = useCompleteApplicationFollowUp();
  const isPending = createMutation.isPending || updateMutation.isPending || completeMutation.isPending;
  const hasError = createMutation.isError || updateMutation.isError || completeMutation.isError;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action.trim() || !dueAt) return;
    const request = { action: action.trim(), due_at: new Date(dueAt).toISOString() };
    if (activeFollowUp) {
      updateMutation.mutate({
        id: applicationId,
        followUpId: activeFollowUp.id,
        followUp: { ...request, expected_version: activeFollowUp.version },
        idempotencyKey: crypto.randomUUID(),
      });
    } else {
      createMutation.mutate({
        id: applicationId,
        followUp: request,
        idempotencyKey: crypto.randomUUID(),
      });
    }
  }

  return (
    <>
      <form className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" onSubmit={save}>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-sm font-medium text-gray-700">Action</span>
          <input
            value={action}
            onChange={(event) => setAction(event.target.value)}
            required
            maxLength={500}
            placeholder="e.g. Call candidate with interview feedback"
            className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">Due date and time</span>
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
            required
            className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </label>
        <div className="flex items-end gap-2">
          <Button type="submit" disabled={isPending || !action.trim() || !dueAt}>
            {isPending ? "Saving…" : activeFollowUp ? "Update follow-up" : "Add follow-up"}
          </Button>
          {activeFollowUp && (
            <Button
              type="button"
              variant="outline"
              disabled={isPending}
              onClick={() => completeMutation.mutate({
                id: applicationId,
                followUpId: activeFollowUp.id,
                followUp: { expected_version: activeFollowUp.version },
                idempotencyKey: crypto.randomUUID(),
              })}
            >
              Mark complete
            </Button>
          )}
        </div>
      </form>
      {hasError && (
        <p role="alert" className="mt-3 text-sm text-red-800">
          We couldn’t save that follow-up. It may have changed; refresh the application and try again.
        </p>
      )}
    </>
  );
}

function ApplicationInterviewsSection({
  applicationId,
  applicationStatus,
}: {
  applicationId: string;
  applicationStatus: ApplicationStatus;
}) {
  const [scheduledStart, setScheduledStart] = useState("");
  const [scheduledEnd, setScheduledEnd] = useState("");
  const [interviewFormat, setInterviewFormat] = useState<InterviewFormat>("online");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [interviewLocation, setInterviewLocation] = useState("");
  const [selectedInterviewers, setSelectedInterviewers] = useState<string[]>([]);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const interviewsQuery = useInterviews({ application_id: applicationId, limit: 25 });
  const interviewersQuery = useTeamInterviewers();
  const scheduleMutation = useScheduleInterview();
  const sessions = interviewsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const interviewerNames = new Map(
    (interviewersQuery.data?.items ?? []).map((interviewer) => [interviewer.id, interviewer.display_name]),
  );
  const startMillis = scheduledStart ? new Date(scheduledStart).getTime() : NaN;
  const endMillis = scheduledEnd ? new Date(scheduledEnd).getTime() : NaN;
  const validFormatDetails = interviewFormat === "online"
    ? Boolean(meetingUrl.trim())
    : Boolean(interviewLocation.trim());
  const validSchedule = Number.isFinite(startMillis) &&
    Number.isFinite(endMillis) &&
    endMillis > startMillis &&
    validFormatDetails &&
    selectedInterviewers.length > 0;

  function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (applicationStatus !== "interview" || !validSchedule) return;
    if (startMillis <= Date.now()) {
      setScheduleError("Choose a future start time for the interview.");
      return;
    }
    setScheduleError(null);
    scheduleMutation.mutate({
      applicationId,
      interview: {
        scheduled_start_at: new Date(scheduledStart).toISOString(),
        scheduled_end_at: new Date(scheduledEnd).toISOString(),
        format: interviewFormat,
        meeting_url: interviewFormat === "online" ? meetingUrl.trim() : null,
        location: interviewFormat === "in_person" ? interviewLocation.trim() : null,
        participants: selectedInterviewers.map((user_id) => ({ user_id, role: "interviewer" })),
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setScheduledStart("");
        setScheduledEnd("");
        setInterviewFormat("online");
        setMeetingUrl("");
        setInterviewLocation("");
        setSelectedInterviewers([]);
      },
    });
  }

  return (
    <section aria-labelledby="application-interviews-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-interviews-heading" className="text-base font-semibold text-sr-text-blue">Interviews</h2>
        <p className="mt-1 text-sm text-gray-600">View scheduled sessions and plan the next conversation.</p>
      </div>

      {interviewsQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading interview sessions…</p>
      ) : interviewsQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">We couldn’t load interview sessions for this application.</p>
          <Button type="button" variant="outline" onClick={() => void interviewsQuery.refetch()}>Try again</Button>
        </div>
      ) : sessions.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600">No interview sessions have been scheduled yet.</p>
      ) : (
        <>
          <ul className="mt-4 divide-y divide-gray-100">
            {sessions.map((interview) => (
              <li key={interview.id} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900">
                    {formatDate(interview.scheduled_start_at)} – {new Intl.DateTimeFormat(undefined, { timeStyle: "short" }).format(new Date(interview.scheduled_end_at))}
                  </p>
                  <p className="mt-1 text-sm text-gray-600">
                    {interview.participants.length
                      ? interview.participants.map((participant) => interviewerNames.get(participant.user_id) ?? "Workspace interviewer").join(", ")
                      : "No interviewer details available"}
                  </p>
                  <p className="mt-1 text-sm text-gray-600">
                    {interview.format === "online"
                      ? "Online"
                      : interview.format === "in_person"
                        ? `In person${interview.location ? ` · ${interview.location}` : ""}`
                        : "Format not specified"}
                  </p>
                  {interview.meeting_url && (
                    <a
                      className="mt-2 inline-flex text-sm font-medium text-sr-text-blue underline"
                      href={interview.meeting_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Join interview
                    </a>
                  )}
                </div>
                <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${interview.status === "scheduled" ? "bg-blue-50 text-blue-800" : interview.status === "completed" ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-700"}`}>
                  {interview.status.replaceAll("_", " ")}
                </span>
              </li>
            ))}
          </ul>
          {interviewsQuery.hasNextPage && (
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              disabled={interviewsQuery.isFetchingNextPage}
              onClick={() => void interviewsQuery.fetchNextPage()}
            >
              {interviewsQuery.isFetchingNextPage ? "Loading…" : "Load more sessions"}
            </Button>
          )}
        </>
      )}

      {applicationStatus === "interview" ? (
        <div className="mt-6 border-t border-gray-100 pt-5">
          <h3 className="text-sm font-semibold text-gray-900">Schedule an interview</h3>
          <p className="mt-1 text-sm text-gray-600">Choose a future time and at least one workspace interviewer.</p>
          {interviewersQuery.isLoading ? (
            <p className="mt-3 text-sm text-gray-500" role="status">Loading available interviewers…</p>
          ) : interviewersQuery.isError ? (
            <div className="mt-3 flex flex-wrap items-center gap-3" role="alert">
              <p className="text-sm text-red-800">We couldn’t load workspace interviewers.</p>
              <Button type="button" variant="outline" onClick={() => void interviewersQuery.refetch()}>Try again</Button>
            </div>
          ) : !interviewersQuery.data?.items.length ? (
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              No interviewers are available. Ask a workspace admin to give a teammate the Interviewer role.
            </p>
          ) : (
            <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={schedule}>
              <label>
                <span className="mb-1 block text-sm font-medium text-gray-700">Starts</span>
                <input
                  type="datetime-local"
                  required
                  value={scheduledStart}
                  onChange={(event) => {
                    setScheduledStart(event.target.value);
                    setScheduleError(null);
                  }}
                  className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                />
              </label>
              <label>
                <span className="mb-1 block text-sm font-medium text-gray-700">Ends</span>
                <input
                  type="datetime-local"
                  required
                  min={scheduledStart || undefined}
                  value={scheduledEnd}
                  onChange={(event) => {
                    setScheduledEnd(event.target.value);
                    setScheduleError(null);
                  }}
                  className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                />
              </label>
              <label className="sm:col-span-2">
                <span className="mb-1 block text-sm font-medium text-gray-700">Interview format</span>
                <select
                  value={interviewFormat}
                  onChange={(event) => {
                    setInterviewFormat(event.target.value as InterviewFormat);
                    setScheduleError(null);
                  }}
                  className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                >
                  <option value="online">Online</option>
                  <option value="in_person">In person</option>
                </select>
              </label>
              {interviewFormat === "online" ? (
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-gray-700">Online meeting link</span>
                  <input
                    type="url"
                    required
                    value={meetingUrl}
                    onChange={(event) => {
                      setMeetingUrl(event.target.value);
                      setScheduleError(null);
                    }}
                    placeholder="https://…"
                    maxLength={2048}
                    className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                  />
                </label>
              ) : (
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-gray-700">Interview location</span>
                  <input
                    required
                    value={interviewLocation}
                    onChange={(event) => {
                      setInterviewLocation(event.target.value);
                      setScheduleError(null);
                    }}
                    maxLength={500}
                    placeholder="Office address or meeting room"
                    className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                  />
                </label>
              )}
              <fieldset className="sm:col-span-2">
                <legend className="mb-2 text-sm font-medium text-gray-700">Interviewers</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {interviewersQuery.data.items.map((interviewer) => (
                    <label key={interviewer.id} className="flex items-center gap-2 rounded-lg border border-gray-200 p-3 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={selectedInterviewers.includes(interviewer.id)}
                        onChange={(event) => setSelectedInterviewers((current) => event.target.checked
                          ? [...current, interviewer.id]
                          : current.filter((id) => id !== interviewer.id))}
                        className="h-4 w-4 rounded border-gray-300 text-sr-green focus:ring-sr-green"
                      />
                      <span>{interviewer.display_name}<span className="block text-xs text-gray-500">{interviewer.email}</span></span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="sm:col-span-2">
                <Button type="submit" disabled={!validSchedule || scheduleMutation.isPending}>
                  {scheduleMutation.isPending ? "Scheduling…" : "Schedule interview"}
                </Button>
              </div>
            </form>
          )}
          {scheduleError && <p className="mt-3 text-sm text-red-800" role="alert">{scheduleError}</p>}
          {scheduleMutation.isSuccess && <p className="mt-3 text-sm text-green-800" role="status">Interview scheduled.</p>}
          {scheduleMutation.isError && <p className="mt-3 text-sm text-red-800" role="alert">We couldn’t schedule this interview. Check the time and interviewer availability, then try again.</p>}
        </div>
      ) : (
        <p className="mt-5 border-t border-gray-100 pt-4 text-sm text-gray-600">
          Move this application to the Interview stage to schedule a session.
        </p>
      )}
    </section>
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
  const { data: session, status: sessionStatus } = useSession();
  const { id } = useParams<{ id: string }>();
  const applicationQuery = useApplication(id);
  const activityQuery = useApplicationActivity(id);
  const teamMembersQuery = useTeamMembers();
  const assignmentMutation = useAssignApplication();
  const application = applicationQuery.data;
  const canReviewInterviewFeedback = session?.roles?.some((role) =>
    role === "tenant_admin" || role === "recruiter" || role === "people_operations",
  ) ?? false;
  const candidateQuery = useCandidate(application?.candidate_id ?? "");
  const documentsQuery = useCandidateDocuments(application?.candidate_id ?? "");
  const downloadMutation = useCandidateDocumentDownload();
  const previewMutation = useCandidateDocumentPreview();
  const requisitionQuery = useRequisition(application?.requisition_id ?? "");
  const candidate = candidateQuery.data;
  const requisition = requisitionQuery.data;
  const assignedMember = teamMembersQuery.data?.items.find(
    (member) => member.id === application?.assigned_to_user_id,
  );
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
            <ApplicationStageControl
              applicationId={application.id}
              status={application.status}
              version={application.version}
            />
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

          <section aria-labelledby="application-owner-heading" className="rounded-xl border border-gray-200 bg-white p-6">
            <h2 id="application-owner-heading" className="text-base font-semibold text-sr-text-blue">Application owner</h2>
            <p className="mt-1 text-sm text-gray-600">Assign a teammate to take responsibility for this application.</p>
            <label className="mt-4 block max-w-md">
              <span className="mb-1 block text-sm font-medium text-gray-700">Assigned recruiter</span>
              <select
                value={application.assigned_to_user_id ?? ""}
                disabled={teamMembersQuery.isLoading || teamMembersQuery.isError || assignmentMutation.isPending}
                onChange={(event) => assignmentMutation.mutate({
                  id: application.id,
                  assignment: {
                    assigned_to_user_id: event.target.value || null,
                    expected_version: application.version,
                  },
                  idempotencyKey: crypto.randomUUID(),
                })}
                className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-700 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20 disabled:cursor-not-allowed disabled:bg-gray-50"
              >
                <option value="">Unassigned</option>
                {teamMembersQuery.data?.items.map((member) => (
                  <option key={member.id} value={member.id}>{member.display_name} · {member.email}</option>
                ))}
                {application.assigned_to_user_id && !assignedMember && (
                  <option value={application.assigned_to_user_id}>Current assignee (not eligible for new assignments)</option>
                )}
              </select>
            </label>
            {teamMembersQuery.isError && (
              <div role="alert" className="mt-2 flex flex-wrap items-center gap-3">
                <p className="text-sm text-red-800">We couldn’t load workspace teammates.</p>
                <Button type="button" variant="outline" onClick={() => void teamMembersQuery.refetch()}>
                  Try again
                </Button>
              </div>
            )}
            {assignmentMutation.isError && (
              <p role="alert" className="mt-2 text-sm text-red-800">
                We couldn’t update the application owner. The application may have changed; reload and try again.
              </p>
            )}
            {assignmentMutation.isSuccess && (
              <p role="status" className="mt-2 text-sm text-green-800">Application owner updated.</p>
            )}
          </section>

          {canReviewInterviewFeedback && (
            <ApplicationScreeningAssessmentSection
              applicationId={application.id}
              applicationStatus={application.status}
              jobTitle={requisition?.title ?? "this role"}
              jobDescription={requisition?.description}
            />
          )}

          <ApplicationFollowUpsSection applicationId={application.id} />

          <ApplicationInterviewsSection
            key={application.id}
            applicationId={application.id}
            applicationStatus={application.status}
          />

          {canReviewInterviewFeedback && (
            <ApplicationInterviewFeedbackSection applicationId={application.id} />
          )}

          <ApplicationDebriefSection
            application={application}
            canReview={canReviewInterviewFeedback}
          />

          {canReviewInterviewFeedback && (
            <ApplicationOfferSection
              applicationId={application.id}
              applicationStatus={application.status}
            />
          )}

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

          <section aria-labelledby="application-activity-heading" className="rounded-xl border border-gray-200 bg-white p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="application-activity-heading" className="text-base font-semibold text-sr-text-blue">Application activity</h2>
                <p className="mt-1 text-sm text-gray-600">A history of this application’s pipeline stage changes.</p>
              </div>
              {activityQuery.isError && (
                <Button type="button" variant="outline" onClick={() => void activityQuery.refetch()}>
                  Try again
                </Button>
              )}
            </div>

            {activityQuery.isLoading ? (
              <p className="mt-5 text-sm text-gray-500" aria-live="polite">Loading application activity…</p>
            ) : activityQuery.isError ? (
              <p role="alert" className="mt-5 text-sm text-red-800">We couldn’t load the application activity. Please try again.</p>
            ) : !activityQuery.data?.items.length ? (
              <p className="mt-5 text-sm text-gray-600">No stage changes have been recorded for this application yet.</p>
            ) : (
              <ol className="mt-5 space-y-5">
                {activityQuery.data.items.map((event) => (
                  <li key={event.id} className="relative flex gap-3">
                    <span aria-hidden="true" className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-sr-green ring-4 ring-sr-mint/30" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-900">
                        {event.from_status
                          ? `Moved from ${STATUS_LABELS[event.from_status]} to ${STATUS_LABELS[event.to_status]}`
                          : `Application submitted · ${STATUS_LABELS[event.to_status]}`}
                      </p>
                      <p className="mt-1 text-xs text-gray-600">
                        {event.actor_display_name} · {formatDate(event.transitioned_at)}
                      </p>
                      {event.rejection_reason && (
                        <p className="mt-2 text-sm text-gray-700">
                          Reason: {REJECTION_REASON_LABELS[event.rejection_reason]}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}
