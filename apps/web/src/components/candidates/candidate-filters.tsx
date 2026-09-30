"use client";

import React from "react";
import type { CandidateStage } from "@/lib/mock-candidates";

const stages: { value: CandidateStage | "all"; label: string }[] = [
  { value: "all", label: "All Candidates" },
  { value: "new", label: "New Applied" },
  { value: "screening", label: "Screening" },
  { value: "interview", label: "Interviewing" },
  { value: "offer", label: "Offered" },
  { value: "hired", label: "Hired" },
  { value: "rejected", label: "Rejected" },
];

const departments = [
  "All Departments",
  "Engineering",
  "Design",
  "Marketing",
  "Sales",
  "People",
];

interface CandidateFiltersProps {
  onStageChange: (stage: CandidateStage | "all") => void;
  onDepartmentChange: (department: string) => void;
  onSearchChange: (query: string) => void;
  activeStage: CandidateStage | "all";
  activeDepartment: string;
  searchQuery: string;
  totalCount: number;
  filteredCount: number;
}

export const CandidateFilters = ({
  onStageChange,
  onDepartmentChange,
  onSearchChange,
  activeStage,
  activeDepartment,
  searchQuery,
  totalCount,
  filteredCount,
}: CandidateFiltersProps) => {
  return (
    <div className="flex flex-col gap-4">
      {/* Stage Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 -mx-1 px-1" style={{ scrollbarWidth: "none", WebkitOverflowScrolling: "touch" }}>
        {stages.map((s) => (
          <button
            key={s.value}
            onClick={() => onStageChange(s.value)}
            className={`px-4 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors shrink-0 ${
              activeStage === s.value
                ? "bg-sr-text-blue text-white"
                : "text-gray-600 hover:bg-gray-100 hover:text-sr-text-blue"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Search and Department Filter */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <svg className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search by name, email, or role..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full h-10 pl-10 pr-4 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all"
          />
        </div>

        {/* Department Dropdown */}
        <select
          value={activeDepartment}
          onChange={(e) => onDepartmentChange(e.target.value)}
          className="h-10 px-4 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 focus:outline-none focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all cursor-pointer w-full sm:w-auto"
        >
          {departments.map((dept) => (
            <option key={dept} value={dept}>
              {dept}
            </option>
          ))}
        </select>

        {/* Result count */}
        <div className="text-sm text-gray-500 whitespace-nowrap hidden lg:block">
          Showing {filteredCount} of {totalCount} candidates
        </div>
      </div>
    </div>
  );
};
