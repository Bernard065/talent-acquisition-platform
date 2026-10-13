"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  useApplicationScreeningAssessments,
  useSubmitApplicationScreeningAssessment,
} from "@/lib/api/hooks/application-screening";
import type {
  ApplicationStatus,
  ScreeningRecommendation,
} from "@/types/api";

const recommendationLabels: Record<ScreeningRecommendation, string> = {
  advance: "Advance to interview",
  hold: "Hold for further review",
  reject: "Do not advance",
};

const ratingLabels = [
  "1 · Limited evidence",
  "2 · Below requirements",
  "3 · Meets requirements",
  "4 · Strong match",
  "5 · Exceptional match",
];

function formatSubmittedAt(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function ApplicationScreeningAssessmentSection({
  applicationId,
  applicationStatus,
  jobTitle,
  jobDescription,
}: {
  applicationId: string;
  applicationStatus: ApplicationStatus;
  jobTitle: string;
  jobDescription?: string | null;
}) {
  const assessmentsQuery = useApplicationScreeningAssessments(applicationId);
  const submitMutation = useSubmitApplicationScreeningAssessment();
  const [criteria, setCriteria] = useState<Record<string, { rating: string; evidence: string }>>({});
  const [overallRating, setOverallRating] = useState("3");
  const [recommendation, setRecommendation] = useState<ScreeningRecommendation>("advance");
  const [summary, setSummary] = useState("");
  const [formError, setFormError] = useState("");
  const hasMyAssessment = Boolean(
    assessmentsQuery.data?.my_assessment_id,
  );
  const rubric = assessmentsQuery.data?.rubric ?? [];
  const rubricVersion = assessmentsQuery.data?.rubric_version;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    if (!rubric.length || rubricVersion === null || rubricVersion === undefined) {
      setFormError("A job screening rubric must be configured before submitting an assessment.");
      return;
    }
    const normalizedCriteria = rubric.map((item) => ({
      criterion_id: item.id,
      rating: Number(criteria[item.id]?.rating ?? "3"),
      evidence: criteria[item.id]?.evidence.trim() || null,
    }));

    try {
      await submitMutation.mutateAsync({
        applicationId,
        assessment: {
          overall_rating: Number(overallRating),
          recommendation,
          rubric_version: rubricVersion,
          criteria: normalizedCriteria,
          summary: summary.trim(),
        },
        idempotencyKey: crypto.randomUUID(),
      });
    } catch {
      setFormError("We couldn’t submit this assessment. The application may have changed or you may already have submitted one.");
    }
  }

  function updateCriterion(id: string, field: "rating" | "evidence", value: string) {
    setCriteria((current) => ({
      ...current,
      [id]: {
        rating: current[id]?.rating ?? "3",
        evidence: current[id]?.evidence ?? "",
        [field]: value,
      },
    }));
  }

  return (
    <section aria-labelledby="application-screening-heading" className="rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 id="application-screening-heading" className="text-base font-semibold text-sr-text-blue">
          Screening assessment
        </h2>
        <p className="mt-1 text-sm text-gray-600">
          Compare the candidate’s evidence with the requirements for {jobTitle} and record your recommendation.
        </p>
      </div>

      <details className="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-4">
        <summary className="cursor-pointer text-sm font-medium text-gray-800">Review job requirements</summary>
        <p className="mt-3 whitespace-pre-wrap text-sm text-gray-700">
          {jobDescription?.trim() || "No job description is available. Use the role requirements agreed with the hiring team."}
        </p>
      </details>

      {assessmentsQuery.isLoading ? (
        <p className="mt-5 text-sm text-gray-500" role="status">Loading screening assessments…</p>
      ) : assessmentsQuery.isError ? (
        <div className="mt-5 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-800">We couldn’t load screening assessments for this application.</p>
          <Button type="button" variant="outline" onClick={() => void assessmentsQuery.refetch()}>Try again</Button>
        </div>
      ) : (
        <>
          {(assessmentsQuery.data?.items.length ?? 0) > 0 && (
            <div className="mt-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-800">Submitted assessments</h3>
              {assessmentsQuery.data?.items.map((assessment) => (
                <article key={assessment.id} className="rounded-lg border border-gray-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-gray-900">{assessment.reviewer_display_name}</p>
                      <p className="mt-1 text-xs text-gray-500">Submitted {formatSubmittedAt(assessment.submitted_at)}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-sr-mint/60 px-3 py-1 text-xs font-semibold text-sr-text-blue">
                        Overall {assessment.overall_rating}/5
                      </span>
                      <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-800">
                        {recommendationLabels[assessment.recommendation]}
                      </span>
                    </div>
                  </div>
                  <ul className="mt-4 space-y-3">
                    {assessment.criteria.map((item) => (
                      <li key={item.criterion} className="border-t border-gray-100 pt-3">
                        <div className="flex flex-wrap justify-between gap-2 text-sm">
                          <span className="font-medium text-gray-800">{item.criterion}</span>
                          <span className="text-gray-600">{item.rating}/5</span>
                        </div>
                        {item.evidence && <p className="mt-1 whitespace-pre-wrap text-sm text-gray-600">{item.evidence}</p>}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 whitespace-pre-wrap border-t border-gray-100 pt-3 text-sm text-gray-700">{assessment.summary}</p>
                </article>
              ))}
            </div>
          )}

          {applicationStatus !== "screening" ? (
            <p className="mt-5 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
              {applicationStatus === "applied"
                ? "Move this application to Screening to submit an assessment."
                : "Screening assessments are closed for this stage. Submitted assessments remain available above."}
            </p>
          ) : hasMyAssessment ? (
            <p className="mt-5 rounded-lg bg-green-50 p-4 text-sm text-green-900" role="status">
              Your screening assessment has been submitted. Submitted assessments are read-only to preserve the review history.
            </p>
          ) : (
            <form className="mt-5 space-y-5 border-t border-gray-100 pt-5" onSubmit={submit}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm font-medium text-gray-700">
                  Overall match
                  <select
                    value={overallRating}
                    onChange={(event) => setOverallRating(event.target.value)}
                    className="mt-2 h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                  >
                    {ratingLabels.map((label, index) => (
                      <option key={label} value={index + 1}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm font-medium text-gray-700">
                  Recommendation
                  <select
                    value={recommendation}
                    onChange={(event) => setRecommendation(event.target.value as ScreeningRecommendation)}
                    className="mt-2 h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                  >
                    {Object.entries(recommendationLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
              </div>

              <div>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-800">Shared job criteria</h3>
                    <p className="mt-1 text-xs text-gray-500">All reviewers use the rubric configured for this job.</p>
                  </div>
                </div>
                {rubric.length ? (
                  <div className="space-y-4">
                    {rubric.map((item, index) => (
                      <fieldset key={item.id} className="rounded-lg border border-gray-200 p-4">
                        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Criterion {index + 1}</legend>
                        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_13rem]">
                          <div>
                            <p className="text-sm font-semibold text-gray-900">{item.criterion}</p>
                            {item.guidance && <p className="mt-1 text-sm text-gray-600">{item.guidance}</p>}
                          </div>
                          <label className="block text-sm font-medium text-gray-700">
                            Match
                            <select
                              value={criteria[item.id]?.rating ?? "3"}
                              onChange={(event) => updateCriterion(item.id, "rating", event.target.value)}
                              className="mt-2 h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                            >
                              {ratingLabels.map((label, ratingIndex) => (
                                <option key={label} value={ratingIndex + 1}>{label}</option>
                              ))}
                            </select>
                          </label>
                        </div>
                        <label className="mt-4 block text-sm font-medium text-gray-700">
                          Evidence from the application
                          <textarea
                            maxLength={2000}
                            rows={2}
                            value={criteria[item.id]?.evidence ?? ""}
                            onChange={(event) => updateCriterion(item.id, "evidence", event.target.value)}
                            placeholder="What in the résumé or application supports this rating?"
                            className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                          />
                        </label>
                      </fieldset>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                    No screening rubric is configured for this job. Ask a recruiter or hiring manager to add shared criteria on the job posting before submitting an assessment.
                  </p>
                )}
              </div>

              <label className="block text-sm font-medium text-gray-700">
                Screening summary
                <textarea
                  required
                  minLength={1}
                  maxLength={5000}
                  rows={4}
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                  placeholder="Summarize the candidate’s fit, strengths, and any concerns for the hiring team."
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
                />
              </label>

              {formError && <p role="alert" className="text-sm text-red-800">{formError}</p>}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-gray-500">Submitted assessments are visible to recruiting teammates and cannot be edited.</p>
                <Button type="submit" disabled={submitMutation.isPending || !summary.trim() || rubric.length === 0}>
                  {submitMutation.isPending ? "Submitting…" : "Submit screening assessment"}
                </Button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
