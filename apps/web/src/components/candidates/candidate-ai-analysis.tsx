import React from "react";
import type { Candidate } from "@/lib/mock-candidates";

export const CandidateAiAnalysis = ({ candidate }: { candidate: Candidate }) => {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-sr-text-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        <h3 className="font-semibold text-gray-900">Neural AI Match</h3>
      </div>

      <div className="flex items-end gap-2 mb-4">
        <span className={`text-4xl font-bold tracking-tight ${candidate.matchScore >= 80 ? 'text-green-600' : candidate.matchScore >= 60 ? 'text-amber-500' : 'text-red-500'}`}>
          {candidate.matchScore}%
        </span>
        <span className="text-gray-500 font-medium mb-1">Match Score</span>
      </div>

      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden mb-5">
        <div 
          className={`h-full rounded-full ${candidate.matchScore >= 80 ? 'bg-green-500' : candidate.matchScore >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
          style={{ width: `${candidate.matchScore}%` }}
        />
      </div>

      <div className="space-y-4">
        <div>
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Key Strengths</h4>
          <ul className="space-y-2">
            <li className="flex items-start gap-2 text-sm text-gray-700">
              <svg className="w-4 h-4 text-green-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Strong background matching required role
            </li>
            <li className="flex items-start gap-2 text-sm text-gray-700">
              <svg className="w-4 h-4 text-green-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Excellent communication skills noted in screening
            </li>
          </ul>
        </div>
        
        <div>
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Potential Gaps</h4>
          <ul className="space-y-2">
            <li className="flex items-start gap-2 text-sm text-gray-700">
              <svg className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Slightly less leadership experience than requested
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
