"use client";

import React from "react";
import type { JobPostingStatus } from "@/types/api/jobs";

const statuses: { value: JobPostingStatus | "all"; label: string }[] = [
  { value: "all", label: "All Jobs" },
  { value: "published", label: "Published" },
  { value: "unpublished", label: "Unpublished" },
  { value: "draft", label: "Draft" },
  { value: "expired", label: "Expired" },
];

interface JobFiltersProps {
  onStatusChange: (status: JobPostingStatus | "all") => void;
  onDepartmentChange: (department: string) => void;
  onSearchChange: (query: string) => void;
  activeStatus: JobPostingStatus | "all";
  activeDepartment: string;
  searchQuery: string;
  totalCount: number;
  filteredCount: number;
  departments: string[];
}

export const JobFilters = ({
  onStatusChange,
  onDepartmentChange,
  onSearchChange,
  activeStatus,
  activeDepartment,
  searchQuery,
  totalCount,
  filteredCount,
  departments,
}: JobFiltersProps) => {
  return (
    <div className="flex flex-col gap-4">
      {/* Status Tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1 -mx-1 px-1" style={{ scrollbarWidth: "none", WebkitOverflowScrolling: "touch" }}>
        {statuses.map((s) => (
          <button
            key={s.value}
            onClick={() => onStatusChange(s.value)}
            className={`px-4 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors shrink-0 ${
              activeStatus === s.value
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
            placeholder="Search jobs by title..."
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
          {["All Departments", ...departments].map((dept) => (
            <option key={dept} value={dept}>
              {dept}
            </option>
          ))}
        </select>

        {/* Result count */}
        <div className="text-sm text-gray-500 whitespace-nowrap hidden lg:block">
          Showing {filteredCount} of {totalCount} jobs
        </div>
      </div>
    </div>
  );
};
