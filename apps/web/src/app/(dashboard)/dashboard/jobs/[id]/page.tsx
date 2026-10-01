import React from "react";
import Link from "next/link";
import { KanbanBoard } from "@/components/jobs/kanban-board";
import { mockCandidates } from "@/lib/mock-candidates";
import { JobStatusBadge } from "@/components/jobs/job-status-badge";

export default async function JobPipelinePage() {
  // In a real app, fetch job details based on ID (using params.id). 
  // For now, we'll mock a job title based on the candidates we have.
  const jobTitle = "Senior Frontend Engineer";
  
  // Filter mock candidates to those that match this job role for realism
  const jobCandidates = mockCandidates.filter(c => c.role === jobTitle || c.role.includes("Frontend"));

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] w-full -m-4 sm:-m-6 md:-m-8 p-4 sm:p-6 md:p-8 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/dashboard/jobs" className="p-2 -ml-2 text-gray-400 hover:text-sr-text-blue transition-colors rounded-lg hover:bg-gray-100">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">{jobTitle}</h1>
              <JobStatusBadge status="active" />
            </div>
            <p className="text-sm text-gray-500 mt-1">
              San Francisco, CA • Full-time • {jobCandidates.length} Candidates
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <button className="h-10 px-4 rounded-lg border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 transition-colors font-medium text-sm">
            Edit Job
          </button>
          <button className="h-10 px-4 rounded-lg bg-sr-mint text-sr-text-blue hover:bg-sr-green hover:text-white transition-colors font-semibold text-sm flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Candidate
          </button>
        </div>
      </div>

      {/* Kanban Board Area */}
      <div className="flex-1 overflow-hidden">
        <KanbanBoard initialCandidates={jobCandidates} />
      </div>
    </div>
  );
}
