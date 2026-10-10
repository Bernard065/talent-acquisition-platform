"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api/errors";
import {
  useScanPublicJobApplicationResume,
  useSubmitPublicJobApplication,
} from "@/lib/api/hooks/public-applications";
import { TurnstileChallenge } from "@/components/careers/turnstile-challenge";

const turnstileRequired = Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY);

type FormValues = {
  fullName: string;
  email: string;
  phone: string;
  location: string;
  privacyConsent: boolean;
};

const MAX_RESUME_BYTES = 10 * 1024 * 1024;
const ALLOWED_RESUME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

function isAllowedResume(file: File): boolean {
  return ALLOWED_RESUME_TYPES.has(file.type) || (
    !file.type && /\.(pdf|docx)$/i.test(file.name)
  );
}

const initialValues: FormValues = {
  fullName: "",
  email: "",
  phone: "",
  location: "",
  privacyConsent: false,
};

function getSubmissionError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "We couldn’t confirm your application. Please try again.";
  }

  if (error.isNotFound) {
    return "This job is no longer accepting applications.";
  }
  if (error.status === 403) {
    return "The security check could not be verified. Complete it again and retry.";
  }
  if (error.status === 422 && error.detail.toLocaleLowerCase().includes("security scan")) {
    return "The résumé did not pass the security scan. Please choose a different file.";
  }
  if (error.status === 422 && error.detail.toLocaleLowerCase().includes("scan")) {
    return "We need to scan this résumé again before submission.";
  }
  if (error.status === 413 || error.isValidationError) {
    return "Please check the information you entered and try again.";
  }
  if (error.status === 429) {
    return "Too many attempts. Please wait a moment before trying again.";
  }
  if (error.status === 503 && error.detail.toLocaleLowerCase().includes("résumé security scanning")) {
    return "We couldn’t scan your résumé right now. Your application was not submitted; please try again shortly.";
  }
  if (error.isRetryable || error.status >= 500) {
    return "Application submission is temporarily unavailable. Please try again shortly.";
  }

  return "We couldn’t submit your application. Please try again.";
}

export function PublicJobApplicationForm({
  publicJobId,
  jobTitle,
}: {
  publicJobId: string;
  jobTitle: string;
}) {
  const [values, setValues] = useState(initialValues);
  const [emailIsValid, setEmailIsValid] = useState(false);
  const [resume, setResume] = useState<File | null>(null);
  const [resumeScanToken, setResumeScanToken] = useState<string | null>(null);
  const [resumeScanRequested, setResumeScanRequested] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [challengeError, setChallengeError] = useState("");
  const [resetChallengeSignal, setResetChallengeSignal] = useState(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  const resumeScanStartedRef = useRef(false);
  const submission = useSubmitPublicJobApplication();
  const resumeScan = useScanPublicJobApplicationResume();
  const scanResume = resumeScan.mutate;
  const canSubmit =
    values.fullName.trim().length > 0 &&
    values.email.trim().length > 0 &&
    emailIsValid &&
    values.privacyConsent &&
    (!turnstileRequired || Boolean(challengeToken) || Boolean(resumeScanToken)) &&
    (!resume || Boolean(resumeScanToken));

  const updateChallengeToken = useCallback((token: string | null) => {
    setChallengeToken(token);
    idempotencyKeyRef.current = null;
    setChallengeError("");
  }, []);

  const updateChallengeError = useCallback((message: string) => {
    setChallengeError(message);
  }, []);

  useEffect(() => {
    if (
      !resume ||
      !resumeScanRequested ||
      resumeScanStartedRef.current ||
      resumeScanToken ||
      resumeScan.isPending ||
      (turnstileRequired && !challengeToken)
    ) {
      return;
    }

    resumeScanStartedRef.current = true;
    const formData = new FormData();
    formData.set("resume", resume);
    formData.set("challenge_token", challengeToken ?? "");
    scanResume({
      publicJobId,
      request: formData,
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: (result) => {
        resumeScanStartedRef.current = false;
        setResumeScanRequested(false);
        setResumeScanToken(result.scan_token);
        setResumeError("");
      },
      onError: (error) => {
        resumeScanStartedRef.current = false;
        setResumeScanRequested(false);
        if (turnstileRequired) {
          setChallengeToken(null);
          setResetChallengeSignal((signal) => signal + 1);
        }
        setResumeError(getSubmissionError(error));
      },
    });
  }, [
    challengeToken,
    publicJobId,
    resume,
    resumeScan.isPending,
    resumeScanRequested,
    resumeScanToken,
    scanResume,
  ]);

  function updateField<Key extends keyof FormValues>(key: Key, value: FormValues[Key]) {
    setValues((current) => ({ ...current, [key]: value }));
    idempotencyKeyRef.current = null;
    submission.reset();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canSubmit || submission.isPending) return;

    if (turnstileRequired && !challengeToken && !resumeScanToken) {
      setChallengeError("Complete the security check before submitting.");
      return;
    }

    if (!idempotencyKeyRef.current) {
      idempotencyKeyRef.current = crypto.randomUUID();
    }

    const formData = new FormData();
    formData.set("full_name", values.fullName.trim());
    formData.set("email", values.email.trim());
    if (values.phone.trim()) formData.set("phone", values.phone.trim());
    if (values.location.trim()) formData.set("location", values.location.trim());
    formData.set("privacy_consent", "true");
    if (!resumeScanToken && challengeToken) formData.set("challenge_token", challengeToken);
    if (resume && resumeScanToken) {
      formData.set("resume", resume);
      formData.set("resume_scan_token", resumeScanToken);
    }

    submission.mutate({
      publicJobId,
      idempotencyKey: idempotencyKeyRef.current,
      request: formData,
    }, {
      onError: (error) => {
        if (error instanceof ApiError && error.status === 403 && turnstileRequired) {
          idempotencyKeyRef.current = null;
          setChallengeToken(null);
          setResetChallengeSignal((signal) => signal + 1);
        }
        if (error instanceof ApiError && error.status === 422 && error.detail.toLowerCase().includes("scan")) {
          setResumeScanToken(null);
          resumeScanStartedRef.current = false;
          setResumeScanRequested(Boolean(resume));
          setChallengeToken(null);
          setResetChallengeSignal((signal) => signal + 1);
        }
      },
    });
  }

  if (submission.isSuccess) {
    return (
      <section aria-live="polite" className="rounded-2xl border border-emerald-200 bg-white p-8 text-center shadow-sm sm:p-10">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-700" aria-hidden="true">
          ✓
        </div>
        <h1 className="mt-5 text-2xl font-bold text-gray-900">Application received</h1>
        <p className="mt-3 text-gray-600">
          Thank you for applying for <strong>{jobTitle}</strong>. Your application has been received.
        </p>
        <Link
          href="/careers"
          className="mt-7 inline-flex items-center justify-center rounded-lg bg-sr-text-blue px-5 py-3 font-semibold text-white transition-colors hover:bg-sr-text-blue/90"
        >
          Browse open roles
        </Link>
      </section>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm sm:p-10">
      <fieldset disabled={submission.isPending} className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor="application-full-name" className="mb-1.5 block text-sm font-medium text-gray-700">
            Full name <span aria-hidden="true">*</span>
          </label>
          <input
            id="application-full-name"
            name="full_name"
            autoComplete="name"
            required
            maxLength={200}
            value={values.fullName}
            onChange={(event) => updateField("fullName", event.target.value)}
            className="h-11 w-full rounded-lg border border-gray-300 px-3 text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="application-email" className="mb-1.5 block text-sm font-medium text-gray-700">
            Email address <span aria-hidden="true">*</span>
          </label>
          <input
            id="application-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={320}
            value={values.email}
            onChange={(event) => {
              updateField("email", event.target.value);
              setEmailIsValid(event.currentTarget.validity.valid);
            }}
            className="h-11 w-full rounded-lg border border-gray-300 px-3 text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </div>

        <div>
          <label htmlFor="application-phone" className="mb-1.5 block text-sm font-medium text-gray-700">
            Phone number <span className="font-normal text-gray-500">(optional)</span>
          </label>
          <input
            id="application-phone"
            name="phone"
            type="tel"
            autoComplete="tel"
            maxLength={50}
            value={values.phone}
            onChange={(event) => updateField("phone", event.target.value)}
            className="h-11 w-full rounded-lg border border-gray-300 px-3 text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </div>

        <div>
          <label htmlFor="application-location" className="mb-1.5 block text-sm font-medium text-gray-700">
            Location <span className="font-normal text-gray-500">(optional)</span>
          </label>
          <input
            id="application-location"
            name="location"
            autoComplete="address-level2"
            maxLength={200}
            value={values.location}
            onChange={(event) => updateField("location", event.target.value)}
            className="h-11 w-full rounded-lg border border-gray-300 px-3 text-gray-900 outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
          />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="application-resume" className="mb-1.5 block text-sm font-medium text-gray-700">
            Résumé <span className="font-normal text-gray-500">(optional, PDF or Word, up to 10 MB)</span>
          </label>
          <input
            id="application-resume"
            name="resume"
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disabled={submission.isPending || resumeScan.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              if (file && !isAllowedResume(file)) {
                setResume(null);
                setResumeScanToken(null);
                resumeScanStartedRef.current = false;
                setResumeScanRequested(false);
                setResumeError("Choose a PDF or Word document.");
                event.target.value = "";
              } else if (file && (file.size === 0 || file.size > MAX_RESUME_BYTES)) {
                setResume(null);
                setResumeScanToken(null);
                resumeScanStartedRef.current = false;
                setResumeScanRequested(false);
                setResumeError("Résumé must be between 1 byte and 10 MB.");
                event.target.value = "";
              } else {
                if (resumeScanToken && challengeToken) {
                  setChallengeToken(null);
                  setResetChallengeSignal((signal) => signal + 1);
                }
                setResume(file);
                setResumeScanToken(null);
                resumeScanStartedRef.current = false;
                setResumeScanRequested(Boolean(file));
                setResumeError("");
                resumeScan.reset();
                idempotencyKeyRef.current = null;
                submission.reset();
              }
            }}
            className="block w-full rounded-lg border border-gray-300 bg-white text-sm text-gray-700 file:mr-4 file:border-0 file:bg-gray-50 file:px-4 file:py-3 file:font-medium file:text-gray-700 hover:file:bg-gray-100"
          />
          {resumeError && <p role="alert" className="mt-2 text-sm text-rose-700">{resumeError}</p>}
          {resume && (
            <div className="mt-3 flex flex-wrap items-center gap-3" aria-live="polite">
              <p className="text-sm text-gray-600">{resume.name}</p>
              {resumeScan.isPending && (
                <span className="text-sm text-gray-600" role="status">Scanning résumé…</span>
              )}
              {resumeScanRequested && turnstileRequired && !challengeToken && !resumeScan.isPending && (
                <span className="text-sm text-gray-600" role="status">Complete the security check to scan your résumé.</span>
              )}
              {resumeScanToken && !resumeScan.isPending && (
                <span className="text-sm font-medium text-emerald-700" role="status">
                  Scan complete.
                </span>
              )}
            </div>
          )}
        </div>
      </fieldset>

      {turnstileRequired && (
        <div className="mt-7">
          <TurnstileChallenge
            onToken={updateChallengeToken}
            onError={updateChallengeError}
            resetSignal={resetChallengeSignal}
          />
          {challengeError && (
            <p role="alert" className="mt-2 text-sm text-rose-700">{challengeError}</p>
          )}
        </div>
      )}

      <div className="mt-8 border-t border-gray-100 pt-6">
        <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-gray-700">
          <input
            name="privacy_consent"
            type="checkbox"
            required
            disabled={submission.isPending}
            checked={values.privacyConsent}
            onChange={(event) => updateField("privacyConsent", event.target.checked)}
            className="mt-1 h-4 w-4 rounded border-gray-300 text-sr-green focus:ring-sr-green"
          />
          <span>
            I consent to the processing of my personal information for this job application.
            <span aria-hidden="true"> *</span>
          </span>
        </label>
        <p className="mt-2 pl-7 text-xs leading-5 text-gray-500">
          Your information will be shared with the hiring workspace so the team can review your application.
        </p>
      </div>

      {submission.isError && (
        <p role="alert" className="mt-5 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {getSubmissionError(submission.error)}
        </p>
      )}

      <div className="mt-7 flex flex-col-reverse gap-3 border-t border-gray-100 pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs text-gray-500">Fields marked * are required.</p>
        </div>
        <button
          type="submit"
          disabled={submission.isPending || !canSubmit}
          className="inline-flex h-12 cursor-pointer items-center justify-center rounded-lg bg-sr-text-blue px-7 font-semibold text-white transition-colors hover:bg-sr-text-blue/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submission.isPending
            ? "Submitting application…"
            : "Submit application"}
        </button>
      </div>
    </form>
  );
}
