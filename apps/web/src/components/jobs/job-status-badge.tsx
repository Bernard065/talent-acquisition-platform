import type { JobPostingStatus } from "@/types/api/jobs";

const statusConfig: Record<JobPostingStatus, { label: string; className: string }> = {
  published: {
    label: "Published",
    className: "bg-green-50 text-green-700 border-green-200",
  },
  unpublished: {
    label: "Unpublished",
    className: "bg-amber-50 text-amber-700 border-amber-200",
  },
  expired: {
    label: "Expired",
    className: "bg-gray-100 text-gray-600 border-gray-200",
  },
  draft: {
    label: "Draft",
    className: "bg-blue-50 text-blue-700 border-blue-200",
  },
};

export const JobStatusBadge = ({ status }: { status: JobPostingStatus }) => {
  const config = statusConfig[status];
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${config.className}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          status === "published"
            ? "bg-green-500"
            : status === "unpublished"
              ? "bg-amber-500"
              : status === "expired"
                ? "bg-gray-400"
                : "bg-blue-500"
        }`}
      />
      {config.label}
    </span>
  );
};
