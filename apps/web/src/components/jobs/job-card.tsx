import { ExtractedSvgIcon23, ExtractedSvgIcon24, ExtractedSvgIcon21, ExtractedSvgIcon10, ExtractedSvgIcon03 } from "@/components/icons";
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
              <ExtractedSvgIcon23 className="w-4 h-4 text-gray-400" />
              {job.department ?? "Department not set"}
            </span>

            {/* Location */}
            <span className="flex items-center gap-1.5">
              <ExtractedSvgIcon24 className="w-4 h-4 text-gray-400" />
              {job.location ?? "Location not set"}
            </span>

            {/* Type */}
            <span className="flex items-center gap-1.5 capitalize">
              <ExtractedSvgIcon21 className="w-4 h-4 text-gray-400" />
              {job.employment_type.replaceAll("_", " ")}
            </span>

            {/* Posted Date */}
            <span className="flex items-center gap-1.5">
              <ExtractedSvgIcon10 className="w-4 h-4 text-gray-400" />
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
            <ExtractedSvgIcon03 className="w-5 h-5" />
          </div>
        </div>
      </div>
    </Link>
  );
};
