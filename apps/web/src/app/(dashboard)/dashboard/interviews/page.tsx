"use client";
import { ExtractedSvgIcon09, ExtractedSvgIcon10 } from "@/components/icons";


import React, { useState } from "react";
import { MOCK_INTERVIEWS } from "@/constants/interviews";
import { InterviewCard } from "@/components/interviews/interview-card";
import type { InterviewTabType } from "@/types/interviews";

export default function InterviewsPage() {
  const [activeTab, setActiveTab] = useState<InterviewTabType>("upcoming");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredInterviews = MOCK_INTERVIEWS.filter((interview) => {
    // Tab filter
    if (activeTab === "upcoming" && interview.status !== "Scheduled") return false;
    if (activeTab === "past" && (interview.status === "Scheduled" || interview.status === "Pending Feedback")) return false;
    if (activeTab === "needs-feedback" && interview.status !== "Pending Feedback") return false;

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        interview.candidateName.toLowerCase().includes(q) ||
        interview.jobTitle.toLowerCase().includes(q) ||
        interview.type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="flex flex-col gap-6 max-w-300 mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Interviews</h1>
          <p className="text-sm text-gray-500 mt-1">Manage your schedule and provide candidate feedback</p>
        </div>

        <div className="relative w-full sm:w-64">
          <input
            type="text"
            placeholder="Search candidate or role..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-10 pl-10 pr-4 rounded-lg border border-gray-200 bg-white text-sm outline-none focus:border-sr-green focus:ring-1 focus:ring-sr-green transition-all"
          />
          <ExtractedSvgIcon09 className="w-4 h-4 text-gray-400 absolute left-3.5 top-3" />
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex items-center gap-6 overflow-x-auto whitespace-nowrap" style={{ scrollbarWidth: "none" }}>
          <button
            onClick={() => setActiveTab("upcoming")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "upcoming" ? "border-sr-green text-sr-text-blue" : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Upcoming
            <span className={`px-2 py-0.5 rounded-full text-xs ${activeTab === "upcoming" ? "bg-sr-mint text-sr-text-blue" : "bg-gray-100 text-gray-500"}`}>
              {MOCK_INTERVIEWS.filter(i => i.status === "Scheduled").length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("needs-feedback")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "needs-feedback" ? "border-sr-green text-sr-text-blue" : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Needs Feedback
            <span className={`px-2 py-0.5 rounded-full text-xs ${activeTab === "needs-feedback" ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500"}`}>
              {MOCK_INTERVIEWS.filter(i => i.status === "Pending Feedback").length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("past")}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "past" ? "border-sr-green text-sr-text-blue" : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Past
            <span className={`px-2 py-0.5 rounded-full text-xs ${activeTab === "past" ? "bg-gray-200 text-gray-700" : "bg-gray-100 text-gray-500"}`}>
              {MOCK_INTERVIEWS.filter(i => i.status === "Completed" || i.status === "Cancelled").length}
            </span>
          </button>
        </nav>
      </div>

      {/* List */}
      <div className="space-y-4 pb-8">
        {filteredInterviews.length > 0 ? (
          filteredInterviews.map((interview) => (
            <InterviewCard
              key={interview.id}
              interview={interview}
              onAction={(action, id) => console.log(action, id)}
            />
          ))
        ) : (
          <div className="text-center py-20 bg-gray-50 rounded-xl border border-gray-100 border-dashed">
            <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm border border-gray-100">
              <ExtractedSvgIcon10 className="w-8 h-8 text-gray-300" />
            </div>
            <h3 className="text-lg font-bold text-gray-700">No interviews found</h3>
            <p className="text-gray-500 mt-1 max-w-sm mx-auto text-sm">
              There are no interviews matching your current filters or search query.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
