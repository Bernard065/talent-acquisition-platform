import React from "react";
import type { Candidate } from "@/lib/mock-candidates";

export const CandidateTimeline = ({ candidate }: { candidate: Candidate }) => {
  const events = [
    {
      id: 1,
      title: "Moved to Interview",
      description: "Scheduled first round interview with hiring manager",
      date: "Oct 1, 2026, 10:30 AM",
      icon: "calendar",
      isPast: candidate.stage !== "new" && candidate.stage !== "screening",
    },
    {
      id: 2,
      title: "Screening Passed",
      description: "Recruiter phone screen completed successfully",
      date: "Sep 29, 2026, 2:15 PM",
      icon: "check",
      isPast: candidate.stage !== "new",
    },
    {
      id: 3,
      title: "Application Received",
      description: "Applied via LinkedIn Careers page",
      date: new Date(candidate.appliedDate).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
      icon: "document",
      isPast: true,
    },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="font-semibold text-gray-900 mb-5">Hiring Journey</h3>

      <div className="relative border-l-2 border-gray-100 ml-3 space-y-6">
        {events.map((event) => (
          <div key={event.id} className="relative pl-6">
            {/* Timeline Dot */}
            <div className={`absolute -left-2.25 top-0.5 w-4 h-4 rounded-full border-2 border-white ${event.isPast ? 'bg-sr-mint' : 'bg-gray-200'}`} />

            <div className="flex flex-col">
              <span className={`text-sm font-medium ${event.isPast ? 'text-gray-900' : 'text-gray-500'}`}>{event.title}</span>
              <span className="text-xs text-gray-500 mt-1">{event.description}</span>
              <span className="text-xs text-gray-400 mt-2">{event.date}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
