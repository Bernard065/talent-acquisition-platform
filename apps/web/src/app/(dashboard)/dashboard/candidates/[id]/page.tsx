"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { ExtractedSvgIcon06, ExtractedSvgIcon07, ExtractedSvgIcon08 } from "@/components/icons";
import { Button } from "@/components/ui/button";
import {
  useCandidate,
  useCandidateTalentPoolConsentState,
  useGrantCandidateTalentPoolConsent,
  useRenewCandidateTalentPoolConsent,
  useRequestCandidateErasure,
  useWithdrawCandidateTalentPoolConsent,
  useWithdrawCandidateConsent,
} from "@/lib/api/hooks/candidates";
import type {
  CandidatePrivacyOperationResponse,
  CandidateTalentPoolCaptureMethod,
} from "@/types/api";

type PrivacyAction = "withdraw" | "erase";
type TalentPoolAction = "grant" | "renew" | "withdraw";
const TALENT_POOL_CAPTURE_METHODS: CandidateTalentPoolCaptureMethod[] = [
  "signed_form",
  "email_confirmation",
  "recruiter_recorded",
];

const getInitials = (name: string): string => {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase() ?? "")
    .join("");
}

const formatValue = (value: string): string => {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const formatDate = (value: string): string => {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(new Date(value));
}

export default function CandidateProfilePage() {
  const { id } = useParams<{ id: string }>();
  const { status: sessionStatus } = useSession();
  const candidateQuery = useCandidate(id);
  const talentPoolConsentQuery = useCandidateTalentPoolConsentState(id);
  const withdrawConsent = useWithdrawCandidateConsent();
  const requestErasure = useRequestCandidateErasure();
  const grantTalentPoolConsent = useGrantCandidateTalentPoolConsent();
  const renewTalentPoolConsent = useRenewCandidateTalentPoolConsent();
  const withdrawTalentPoolConsent = useWithdrawCandidateTalentPoolConsent();
  const candidate = candidateQuery.data;
  const isLoading = sessionStatus !== "authenticated" || candidateQuery.isLoading;
  const [pendingPrivacyAction, setPendingPrivacyAction] = useState<PrivacyAction | null>(null);
  const [pendingTalentPoolAction, setPendingTalentPoolAction] = useState<TalentPoolAction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [talentPoolCaptureMethod, setTalentPoolCaptureMethod] = useState<CandidateTalentPoolCaptureMethod | "">("");
  const [talentPoolNoticeVersion, setTalentPoolNoticeVersion] = useState("");
  const [erasureResult, setErasureResult] = useState<CandidatePrivacyOperationResponse | null>(null);
  const isMutating = withdrawConsent.isPending || requestErasure.isPending ||
    grantTalentPoolConsent.isPending || renewTalentPoolConsent.isPending ||
    withdrawTalentPoolConsent.isPending;
  const erasureMessage = erasureResult?.privacy_status === "erasure_pending"
    ? "The erasure request has been accepted. The candidate has entered the erasure process, and document cleanup is being handled asynchronously."
    : "The candidate’s data has been erased.";

  function resetTalentPoolForm() {
    setTalentPoolCaptureMethod("");
    setTalentPoolNoticeVersion("");
  }

  function openTalentPoolAction(action: TalentPoolAction) {
    setActionError(null);
    resetTalentPoolForm();
    setPendingPrivacyAction(null);
    setPendingTalentPoolAction(action);
  }

  function closePrivacyDialog() {
    setPendingPrivacyAction(null);
    setPendingTalentPoolAction(null);
    resetTalentPoolForm();
    setActionError(null);
  }

  async function confirmPrivacyAction() {
    if (!pendingPrivacyAction && !pendingTalentPoolAction) return;
    setActionError(null);
    try {
      const idempotencyKey = crypto.randomUUID();
      if (pendingPrivacyAction === "withdraw") {
        await withdrawConsent.mutateAsync({ id, idempotencyKey });
        setActionNotice("Candidate data-processing consent has been withdrawn.");
      } else if (pendingPrivacyAction === "erase") {
        const result = await requestErasure.mutateAsync({ id, idempotencyKey });
        setErasureResult(result);
        setActionNotice(null);
      } else if (pendingTalentPoolAction === "grant" || pendingTalentPoolAction === "renew") {
        if (!talentPoolCaptureMethod || !talentPoolNoticeVersion.trim()) {
          setActionError("Select an evidence method and enter the consent notice version.");
          return;
        }
        const variables = {
          id,
          idempotencyKey,
          body: {
            capture_method: talentPoolCaptureMethod,
            notice_version: talentPoolNoticeVersion.trim(),
          },
        };
        const result = pendingTalentPoolAction === "grant"
          ? await grantTalentPoolConsent.mutateAsync(variables)
          : await renewTalentPoolConsent.mutateAsync(variables);
        setActionNotice(`Talent-pool consent ${formatValue(result.event_type)} event recorded.`);
      } else {
        if (!talentPoolCaptureMethod) {
          setActionError("Select an evidence method before recording the withdrawal.");
          return;
        }
        const result = await withdrawTalentPoolConsent.mutateAsync({
          id,
          idempotencyKey,
          body: { capture_method: talentPoolCaptureMethod },
        });
        setActionNotice(`Talent-pool consent ${formatValue(result.event_type)} event recorded.`);
      }
      setPendingPrivacyAction(null);
      setPendingTalentPoolAction(null);
      resetTalentPoolForm();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The privacy action could not be completed.");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <Link
        href="/dashboard/candidates"
        className="flex w-fit items-center gap-1 text-sm font-medium text-gray-500 transition-colors hover:text-sr-text-blue"
      >
        <ExtractedSvgIcon06 className="h-4 w-4" />
        Back to Candidates
      </Link>

      {erasureResult ? (
        <section role="status" className="rounded-xl border border-green-200 bg-green-50 p-8">
          <h1 className="text-lg font-semibold text-green-950">
            {erasureResult.privacy_status === "erasure_pending" ? "Erasure request received" : "Candidate data erased"}
          </h1>
          <p className="mt-2 text-sm text-green-900">
            {erasureMessage} Privacy status: {formatValue(erasureResult.privacy_status)}.
          </p>
          <Link className="mt-5 inline-flex text-sm font-semibold text-sr-text-blue underline" href="/dashboard/candidates">
            Return to candidates
          </Link>
        </section>
      ) : isLoading ? (
        <div
          className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500"
          aria-live="polite"
        >
          Loading candidate profile…
        </div>
      ) : candidateQuery.isError || !candidate ? (
        <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <h1 className="text-lg font-semibold text-red-900">Candidate unavailable</h1>
          <p className="mt-2 text-sm text-red-800">
            This profile may have been removed, or you may not have access to it.
          </p>
          <Button
            className="mt-5"
            variant="outline"
            onClick={() => void candidateQuery.refetch()}
          >
            Try again
          </Button>
        </section>
      ) : (
        <>
          <header className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
            <div className="flex items-start gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-sr-mint text-2xl font-bold text-sr-text-blue">
                {getInitials(candidate.full_name) || "?"}
              </div>
              <div className="min-w-0">
                <h1 className="wrap-break-word text-2xl font-bold tracking-tight text-gray-900">
                  {candidate.full_name}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-600">
                  <span className="flex items-center gap-1.5">
                    <ExtractedSvgIcon08 className="h-4 w-4 text-gray-400" />
                    {candidate.email}
                  </span>
                  {candidate.location && (
                    <span className="flex items-center gap-1.5">
                      <ExtractedSvgIcon07 className="h-4 w-4 text-gray-400" />
                      {candidate.location}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </header>

          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
            <h2 className="text-lg font-semibold text-sr-text-blue">Candidate details</h2>
            <dl className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Phone</dt>
                <dd className="mt-1 wrap-break-word text-sm text-gray-900">
                  {candidate.phone || "Not provided"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Location</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {candidate.location || "Not provided"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Source</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatValue(candidate.source)}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Added</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatDate(candidate.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">Last updated</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatDate(candidate.updated_at)}</dd>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
            <h2 className="text-lg font-semibold text-sr-text-blue">Privacy &amp; consent</h2>
            {actionNotice && <p role="status" className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-900">{actionNotice}</p>}
            {actionError && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{actionError}</p>}

            <div className="mt-5 flex flex-col gap-4 border-b border-gray-100 pb-6 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-medium text-gray-900">Candidate data-processing consent</h3>
                <p className="mt-1 text-sm text-gray-600">Current status: {formatValue(candidate.consent_status)}.</p>
                <p className="mt-1 text-xs text-gray-500">Talent-pool consent is managed separately and is not represented by this status.</p>
              </div>
              <Button
                variant="outline"
                disabled={candidate.consent_status === "withdrawn" || isMutating}
                onClick={() => { setActionError(null); setPendingPrivacyAction("withdraw"); }}
              >
                {candidate.consent_status === "withdrawn" ? "Consent withdrawn" : "Withdraw consent"}
              </Button>
            </div>

            <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-medium text-gray-900">Data privacy</h3>
                <p className="mt-1 max-w-2xl text-sm text-gray-600">Request erasure to anonymize this candidate and begin document cleanup. This action cannot be undone.</p>
              </div>
              <Button
                variant="destructive"
                disabled={isMutating}
                onClick={() => { setActionError(null); setPendingPrivacyAction("erase"); }}
              >
                Request erasure
              </Button>
            </div>

            <div className="mt-6 border-t border-gray-100 pt-6">
              <h3 className="font-medium text-gray-900">Talent-pool consent</h3>
              <p className="mt-1 text-sm text-gray-600">
                This consent is separate from general candidate data-processing consent. Record the event that matches the candidate’s documented evidence.
              </p>
              {talentPoolConsentQuery.isLoading ? (
                <p className="mt-3 text-sm text-gray-500" aria-live="polite">Loading talent-pool consent status…</p>
              ) : talentPoolConsentQuery.isError || !talentPoolConsentQuery.data ? (
                <div className="mt-3" role="alert">
                  <p className="text-sm text-red-800">Talent-pool consent status could not be loaded. Actions are unavailable.</p>
                  <Button className="mt-2" variant="outline" onClick={() => void talentPoolConsentQuery.refetch()}>Try again</Button>
                </div>
              ) : (
                <>
                  <p className="mt-2 text-sm text-gray-700">
                    Status: <span className="font-medium">{formatValue(talentPoolConsentQuery.data.status)}</span>
                    {talentPoolConsentQuery.data.event_version !== null && ` · Event ${talentPoolConsentQuery.data.event_version}`}
                  </p>
                  {talentPoolConsentQuery.data.recorded_at && (
                    <p className="mt-1 text-xs text-gray-500">
                      Last recorded {formatDate(talentPoolConsentQuery.data.recorded_at)}
                      {talentPoolConsentQuery.data.capture_method && ` · ${formatValue(talentPoolConsentQuery.data.capture_method)}`}
                      {talentPoolConsentQuery.data.notice_version && ` · Notice ${talentPoolConsentQuery.data.notice_version}`}
                    </p>
                  )}
                </>
              )}
              <div className="mt-4 flex flex-wrap gap-3">
                {talentPoolConsentQuery.data?.status !== "granted" && (
                  <Button variant="outline" disabled={isMutating || talentPoolConsentQuery.isLoading || talentPoolConsentQuery.isError} onClick={() => openTalentPoolAction("grant")}>
                    Record grant
                  </Button>
                )}
                {talentPoolConsentQuery.data?.status === "granted" && (
                  <>
                    <Button variant="outline" disabled={isMutating || talentPoolConsentQuery.isLoading || talentPoolConsentQuery.isError} onClick={() => openTalentPoolAction("renew")}>
                      Record renewal
                    </Button>
                    <Button variant="outline" disabled={isMutating || talentPoolConsentQuery.isLoading || talentPoolConsentQuery.isError} onClick={() => openTalentPoolAction("withdraw")}>
                      Record withdrawal
                    </Button>
                  </>
                )}
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
            <h2 className="text-base font-semibold text-sr-text-blue">Hiring activity and documents</h2>
            <p className="mt-2 text-sm text-gray-600">
              Activity history and candidate documents aren’t available in this profile yet.
            </p>
          </section>
        </>
      )}

      {(pendingPrivacyAction || pendingTalentPoolAction) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="privacy-confirm-title"
            aria-describedby="privacy-confirm-description"
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
          >
            <h2 id="privacy-confirm-title" className="text-lg font-semibold text-gray-900">
              {pendingPrivacyAction === "withdraw" ? "Withdraw candidate consent?"
                : pendingPrivacyAction === "erase" ? "Request candidate erasure?"
                  : pendingTalentPoolAction === "grant" ? "Record talent-pool consent grant?"
                    : pendingTalentPoolAction === "renew" ? "Renew talent-pool consent?"
                      : "Withdraw talent-pool consent?"}
            </h2>
            <p id="privacy-confirm-description" className="mt-3 text-sm text-gray-600">
              {pendingPrivacyAction === "withdraw"
                ? "This records withdrawal of the candidate’s general data-processing consent. Their profile remains in the workspace. Talent-pool consent is separate."
                : pendingPrivacyAction === "erase"
                  ? "This anonymizes the candidate’s personal information and starts document cleanup. This action cannot be undone."
                  : "Confirm that the selected event reflects the candidate’s documented evidence. The event is recorded in the talent-pool consent history."}
            </p>
            {pendingTalentPoolAction && (
              <div className="mt-4 space-y-4">
                <dl className="rounded-md bg-gray-50 p-3 text-sm">
                  <div className="flex justify-between gap-4"><dt className="text-gray-500">Evidence method</dt><dd className="font-medium text-gray-900">{talentPoolCaptureMethod ? formatValue(talentPoolCaptureMethod) : "Not selected"}</dd></div>
                  {pendingTalentPoolAction !== "withdraw" && <div className="mt-2 flex justify-between gap-4"><dt className="text-gray-500">Notice version</dt><dd className="font-medium text-gray-900">{talentPoolNoticeVersion.trim() || "Not entered"}</dd></div>}
                </dl>
                <label className="block text-sm font-medium text-gray-700">
                  Evidence method
                  <select
                    className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                    value={talentPoolCaptureMethod}
                    onChange={(event) => setTalentPoolCaptureMethod(event.target.value as CandidateTalentPoolCaptureMethod | "")}
                  >
                    <option value="">Select evidence method</option>
                    {TALENT_POOL_CAPTURE_METHODS.map((method) => (
                      <option key={method} value={method}>{formatValue(method)}</option>
                    ))}
                  </select>
                </label>
                {pendingTalentPoolAction !== "withdraw" && (
                  <label className="block text-sm font-medium text-gray-700">
                    Consent notice version
                    <input
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      value={talentPoolNoticeVersion}
                      onChange={(event) => setTalentPoolNoticeVersion(event.target.value)}
                      maxLength={100}
                      required
                    />
                  </label>
                )}
              </div>
            )}
            {actionError && <p role="alert" className="mt-3 text-sm text-red-700">{actionError}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" disabled={isMutating} onClick={closePrivacyDialog}>Cancel</Button>
              <Button
                variant={pendingPrivacyAction === "erase" ? "destructive" : "default"}
                disabled={isMutating || (Boolean(pendingTalentPoolAction) && (!talentPoolCaptureMethod || (pendingTalentPoolAction !== "withdraw" && !talentPoolNoticeVersion.trim())))}
                onClick={() => void confirmPrivacyAction()}
              >
                {isMutating ? "Processing…" : pendingPrivacyAction === "withdraw" || pendingTalentPoolAction === "withdraw" ? "Confirm withdrawal"
                  : pendingPrivacyAction === "erase" ? "Confirm erasure" : pendingTalentPoolAction === "renew" ? "Confirm renewal" : "Confirm grant"}
              </Button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
