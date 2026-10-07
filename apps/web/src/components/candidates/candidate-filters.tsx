"use client";
import { ExtractedSvgIcon09 } from "@/components/icons";


import React from "react";
interface CandidateFiltersProps {
  onSearchChange: (query: string) => void;
  onSourceChange: (source: string) => void;
  onLocationChange: (location: string) => void;
  searchQuery: string;
  source: string;
  location: string;
  sourceOptions: string[];
  locationOptions: string[];
}

export const CandidateFilters = ({
  onSearchChange,
  onSourceChange,
  onLocationChange,
  searchQuery,
  source,
  location,
  sourceOptions,
  locationOptions,
}: CandidateFiltersProps) => {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col lg:flex-row items-stretch gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-56">
          <ExtractedSvgIcon09 className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            aria-label="Search candidates by name or email"
            placeholder="Search by name or email..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full h-10 pl-10 pr-4 rounded-lg border border-gray-200 bg-white text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all"
          />
        </div>

        <select
          aria-label="Filter candidates by source"
          value={source}
          onChange={(e) => onSourceChange(e.target.value)}
          className="h-10 px-4 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all w-full lg:w-52"
        >
          <option value="">All sources</option>
          {sourceOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>

        <select
          aria-label="Filter candidates by location"
          value={location}
          onChange={(e) => onLocationChange(e.target.value)}
          className="h-10 px-4 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:border-sr-mint focus:ring-1 focus:ring-sr-mint transition-all w-full lg:w-52"
        >
          <option value="">All locations</option>
          {locationOptions.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </div>
    </div>
  );
};
