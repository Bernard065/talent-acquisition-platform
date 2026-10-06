import Link from "next/link";
import type { JobPostingResponse } from "@/types/api/jobs";
import { JobStatusBadge } from "./job-status-badge";

export const JobCard = ({ job }: { job: JobPostingResponse }) => {
  const postedDate = new Date(job.published_at ?? job.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <Link
      href={`/dashboard/jobs/${job.id}`}
      className="block bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md hover:border-gray-300 transition-all group"
    >
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        {/* Left side */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <h3 className="text-base font-semibold text-sr-text-blue group-hover:text-sr-green transition-colors break-words">
              {job.title}
            </h3>
            <JobStatusBadge status={job.status} />
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-500">
            {/* Department */}
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              {job.department ?? "Department not set"}
            </span>

            {/* Location */}
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {job.location ?? "Location not set"}
            </span>

            {/* Type */}
            <span className="flex items-center gap-1.5 capitalize">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {job.employment_type.replaceAll("_", " ")}
            </span>

            {/* Posted Date */}
            <span className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Posted {postedDate}
            </span>
          </div>
        </div>

        {/* Right side - Applicant counts */}
        <div className="flex items-center gap-4 sm:gap-6 shrink-0 pt-3 sm:pt-0 border-t sm:border-t-0 border-gray-100">
          <div className="text-xs text-gray-500">
            Updated {new Date(job.updated_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          </div>
          <div className="hidden sm:flex items-center text-gray-300 group-hover:text-sr-green transition-colors ml-auto sm:ml-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>
      </div>
    </Link>
  );
};
