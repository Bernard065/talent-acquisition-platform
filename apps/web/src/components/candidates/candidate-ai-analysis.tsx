import { ExtractedSvgIcon18, ExtractedSvgIcon19, ExtractedSvgIcon20 } from "@/components/icons";
import React from "react";
import type { Candidate } from "@/lib/mock-candidates";

export const CandidateAiAnalysis = ({ candidate }: { candidate: Candidate }) => {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <ExtractedSvgIcon18 className="w-5 h-5 text-sr-text-blue" />
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
              <ExtractedSvgIcon19 className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
              Strong background matching required role
            </li>
            <li className="flex items-start gap-2 text-sm text-gray-700">
              <ExtractedSvgIcon19 className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
              Excellent communication skills noted in screening
            </li>
          </ul>
        </div>
        
        <div>
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Potential Gaps</h4>
          <ul className="space-y-2">
            <li className="flex items-start gap-2 text-sm text-gray-700">
              <ExtractedSvgIcon20 className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
              Slightly less leadership experience than requested
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
