"use client";

import React, { useState } from "react";
import { PIPELINE_REPORTS } from "@/constants/analytics";

export const DetailedPipeline = () => {
  const [selectedJobId, setSelectedJobId] = useState<string>(PIPELINE_REPORTS[0]?.jobId || "");

  const currentReport = PIPELINE_REPORTS.find(r => r.jobId === selectedJobId);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col h-full overflow-hidden">
      <div className="p-6 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-sr-text-blue">Detailed Pipeline Report</h2>
          <p className="text-sm text-gray-500 mt-1">Candidate progression and bottleneck analysis</p>
        </div>
        <div>
          <select 
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
            className="h-10 px-4 rounded-lg border border-gray-200 bg-gray-50 text-sm outline-none focus:border-sr-green font-medium text-gray-700 w-full sm:w-64"
          >
            {PIPELINE_REPORTS.map(report => (
              <option key={report.jobId} value={report.jobId}>
                {report.jobTitle}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[600px]">
          <thead>
            <tr className="bg-gray-50/50 border-b border-gray-100">
              <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Candidate</th>
              <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Current Stage</th>
              <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Time in Stage</th>
              <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Match Score</th>
              <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {currentReport?.candidates.map(candidate => (
              <tr key={candidate.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center font-bold text-xs text-gray-600">
                      {candidate.initials}
                    </div>
                    <span className="font-semibold text-gray-900 text-sm">{candidate.name}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className="text-sm text-gray-700 font-medium">{candidate.stage}</span>
                </td>
                <td className="px-6 py-4">
                  <span className="text-sm text-gray-500">{candidate.timeInStage}</span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-16 bg-gray-100 rounded-full h-2">
                      <div 
                        className={`h-2 rounded-full ${candidate.matchScore >= 90 ? 'bg-emerald-500' : candidate.matchScore >= 80 ? 'bg-amber-500' : 'bg-red-500'}`} 
                        style={{ width: `${candidate.matchScore}%` }}
                      ></div>
                    </div>
                    <span className="text-sm font-semibold text-gray-700">{candidate.matchScore}%</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-right">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                    candidate.status === 'On Track' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                    candidate.status === 'Slipping' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                    'bg-red-50 text-red-700 border-red-200'
                  }`}>
                    {candidate.status}
                  </span>
                </td>
              </tr>
            ))}
            
            {(!currentReport || currentReport.candidates.length === 0) && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500 text-sm">
                  No candidates found in the pipeline for this job.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
