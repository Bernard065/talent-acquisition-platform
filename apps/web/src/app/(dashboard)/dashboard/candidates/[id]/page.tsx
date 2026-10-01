import React from "react";
import Link from "next/link";
import { mockCandidates } from "@/lib/mock-candidates";
import { CandidateStageBadge } from "@/components/candidates/candidate-stage-badge";
import { CandidateAiAnalysis } from "@/components/candidates/candidate-ai-analysis";
import { CandidateTimeline } from "@/components/candidates/candidate-timeline";

export default async function CandidateProfilePage(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  const candidateId = params.id;

  // Find candidate or default to first one for demo purposes
  const candidate = mockCandidates.find(c => c.id === candidateId) || mockCandidates[0];

  return (
    <div className="flex flex-col gap-6 max-w-300 mx-auto w-full">

      {/* Header and Back Link */}
      <div className="flex flex-col gap-4">
        <Link href="/dashboard/candidates" className="text-sm font-medium text-gray-500 hover:text-sr-text-blue transition-colors flex items-center gap-1 w-fit">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Candidates
        </Link>

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-2xl shrink-0">
              {candidate.initials}
            </div>
            <div className="flex flex-col">
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{candidate.name}</h1>
              <div className="text-sm text-gray-500 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {candidate.role}
                </span>
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {candidate.email}
                </span>
              </div>
              <div className="mt-3">
                <CandidateStageBadge stage={candidate.stage} />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 md:ml-auto">
            <button className="h-10 px-4 rounded-lg border border-red-200 text-red-700 bg-red-50 hover:bg-red-100 transition-colors font-medium text-sm">
              Reject
            </button>
            <button className="h-10 px-4 rounded-lg border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 transition-colors font-medium text-sm">
              Message
            </button>
            <button className="h-10 px-4 rounded-lg bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white transition-colors font-semibold text-sm">
              Advance to Offer
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left Column (Resume/Details) - Takes up 2/3 */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col min-h-150">
            <div className="border-b border-gray-200 bg-gray-50 p-3 flex gap-2 overflow-x-auto whitespace-nowrap" style={{ scrollbarWidth: "none" }}>
              <button className="px-4 py-1.5 text-sm font-medium bg-white border border-gray-200 rounded shadow-sm text-gray-900">
                Resume / CV
              </button>
              <button className="px-4 py-1.5 text-sm font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors">
                Application Answers
              </button>
              <button className="px-4 py-1.5 text-sm font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors">
                Scorecards
              </button>
            </div>

            {/* Mock Resume Viewer */}
            <div className="flex-1 bg-gray-100 p-6 sm:p-10 flex justify-center">
              <div className="bg-white w-full max-w-200 shadow-sm border border-gray-200 h-full p-8 sm:p-12">
                <div className="w-1/2 h-8 bg-gray-200 rounded mb-4" />
                <div className="w-1/3 h-4 bg-gray-200 rounded mb-10" />

                <div className="w-32 h-5 bg-gray-200 rounded mb-6" />
                <div className="w-full h-4 bg-gray-100 rounded mb-3" />
                <div className="w-full h-4 bg-gray-100 rounded mb-3" />
                <div className="w-5/6 h-4 bg-gray-100 rounded mb-10" />

                <div className="w-32 h-5 bg-gray-200 rounded mb-6" />
                <div className="w-full h-4 bg-gray-100 rounded mb-3" />
                <div className="w-full h-4 bg-gray-100 rounded mb-3" />
                <div className="w-3/4 h-4 bg-gray-100 rounded mb-3" />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (Analysis/Timeline) - Takes up 1/3 */}
        <div className="lg:col-span-1 flex flex-col">
          <CandidateAiAnalysis candidate={candidate} />
          <CandidateTimeline candidate={candidate} />
        </div>

      </div>
    </div>
  );
}
