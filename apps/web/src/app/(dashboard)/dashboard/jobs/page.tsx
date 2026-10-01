"use client";

import React, { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { mockJobs } from "@/lib/mock-jobs";
import type { JobStatus } from "@/lib/mock-jobs";
import { JobFilters } from "@/components/jobs/job-filters";
import { JobCard } from "@/components/jobs/job-card";
import Link from "next/link";

export default function JobsPage() {
  const [activeStatus, setActiveStatus] = useState<JobStatus | "all">("all");
  const [activeDepartment, setActiveDepartment] = useState("All Departments");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredJobs = useMemo(() => {
    return mockJobs.filter((job) => {
      const matchesStatus = activeStatus === "all" || job.status === activeStatus;
      const matchesDepartment =
        activeDepartment === "All Departments" || job.department === activeDepartment;
      const matchesSearch =
        searchQuery === "" ||
        job.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        job.department.toLowerCase().includes(searchQuery.toLowerCase()) ||
        job.location.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStatus && matchesDepartment && matchesSearch;
    });
  }, [activeStatus, activeDepartment, searchQuery]);

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Jobs</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your open positions and track applicants
          </p>
        </div>
        <Button
          variant="secondary"
          className="h-10 bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white transition-colors font-semibold gap-2 w-full sm:w-auto"
          asChild
        >
          <Link href="/dashboard/jobs/new">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create New Job
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <JobFilters
        onStatusChange={setActiveStatus}
        onDepartmentChange={setActiveDepartment}
        onSearchChange={setSearchQuery}
        activeStatus={activeStatus}
        activeDepartment={activeDepartment}
        searchQuery={searchQuery}
        totalCount={mockJobs.length}
        filteredCount={filteredJobs.length}
      />

      {/* Job Cards List */}
      <div className="flex flex-col gap-3">
        {filteredJobs.length > 0 ? (
          filteredJobs.map((job) => <JobCard key={job.id} job={job} />)
        ) : (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
            <div className="mx-auto w-14 h-14 bg-gray-50 rounded-full flex items-center justify-center mb-4">
              <svg className="w-7 h-7 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-sr-text-blue mb-1">No jobs found</h3>
            <p className="text-sm text-gray-500">
              Try adjusting your search or filters to find what you&apos;re looking for.
            </p>
          </div>
        )}
      </div>

      {/* Results count on mobile */}
      <div className="text-sm text-gray-500 text-center lg:hidden">
        Showing {filteredJobs.length} of {mockJobs.length} jobs
      </div>
    </div>
  );
}
