"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { JobFilters } from "@/components/jobs/job-filters";
import { JobCard } from "@/components/jobs/job-card";
import { useJobPostings } from "@/lib/api/hooks/jobs";
import type { JobPostingStatus } from "@/types/api/jobs";

export default function JobsPage() {
  const { status: sessionStatus } = useSession();
  const postingsQuery = useJobPostings({ limit: 100 });
  const postings = useMemo(
    () => postingsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [postingsQuery.data],
  );
  const [activeStatus, setActiveStatus] = useState<JobPostingStatus | "all">("all");
  const [activeDepartment, setActiveDepartment] = useState("All Departments");
  const [searchQuery, setSearchQuery] = useState("");
  const isLoading = sessionStatus !== "authenticated" || postingsQuery.isLoading;
  const error = postingsQuery.isError
    ? "We couldn’t load jobs from your workspace. Please try again."
    : null;

  const departments = useMemo(
    () => Array.from(new Set(postings.map((posting) => posting.department).filter((value): value is string => Boolean(value)))).sort(),
    [postings],
  );

  const filteredPostings = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return postings.filter((posting) => {
      const matchesStatus = activeStatus === "all" || posting.status === activeStatus;
      const matchesDepartment = activeDepartment === "All Departments" || posting.department === activeDepartment;
      const matchesSearch = !query || [posting.title, posting.department, posting.location]
        .some((value) => value?.toLocaleLowerCase().includes(query));
      return matchesStatus && matchesDepartment && matchesSearch;
    });
  }, [postings, activeStatus, activeDepartment, searchQuery]);

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto w-full">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sr-text-blue tracking-tight">Jobs</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage job postings created from approved requisitions
          </p>
        </div>
        <Button
          variant="secondary"
          className="h-10 bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white transition-colors font-semibold gap-2 w-full sm:w-auto"
          asChild
        >
          <Link href="/dashboard/jobs/new">
            <span aria-hidden="true">+</span>
            Create requisition
          </Link>
        </Button>
      </div>

      <JobFilters
        onStatusChange={setActiveStatus}
        onDepartmentChange={setActiveDepartment}
        onSearchChange={setSearchQuery}
        activeStatus={activeStatus}
        activeDepartment={activeDepartment}
        searchQuery={searchQuery}
        totalCount={postings.length}
        filteredCount={filteredPostings.length}
        departments={departments}
      />

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-sm text-red-800">{error}</p>
          <Button className="mt-4" variant="outline" onClick={() => void postingsQuery.refetch()}>
            Try again
          </Button>
        </div>
      ) : isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500" aria-live="polite">
          Loading jobs…
        </div>
      ) : filteredPostings.length ? (
        <>
          <div className="flex flex-col gap-3">
            {filteredPostings.map((posting) => <JobCard key={posting.id} job={posting} />)}
          </div>
          {postingsQuery.hasNextPage && (
            <div className="flex justify-center">
              <Button
                variant="outline"
                disabled={postingsQuery.isFetchingNextPage}
                onClick={() => void postingsQuery.fetchNextPage()}
              >
                {postingsQuery.isFetchingNextPage ? "Loading…" : "Load more jobs"}
              </Button>
            </div>
          )}
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <h2 className="text-base font-semibold text-sr-text-blue mb-1">
            {postings.length ? "No jobs match these filters" : "No job postings yet"}
          </h2>
          <p className="text-sm text-gray-500">
            {postings.length
              ? "Adjust your search or filters to see more results."
              : "Create a requisition and turn it into a job posting when it is approved."}
          </p>
          {!postings.length && (
            <Button className="mt-4" variant="outline" asChild>
              <Link href="/dashboard/jobs/new">Create a requisition</Link>
            </Button>
          )}
        </div>
      )}

      <div className="text-sm text-gray-500 text-center lg:hidden">
        Showing {filteredPostings.length} of {postings.length} jobs
      </div>
    </div>
  );
}
