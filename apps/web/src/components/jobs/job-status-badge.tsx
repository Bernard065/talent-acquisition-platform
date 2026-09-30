import type { JobStatus } from "@/lib/mock-jobs";

const statusConfig: Record<JobStatus, { label: string; className: string }> = {
  active: {
    label: "Active",
    className: "bg-green-50 text-green-700 border-green-200",
  },
  paused: {
    label: "Paused",
    className: "bg-amber-50 text-amber-700 border-amber-200",
  },
  closed: {
    label: "Closed",
    className: "bg-gray-100 text-gray-600 border-gray-200",
  },
  draft: {
    label: "Draft",
    className: "bg-blue-50 text-blue-700 border-blue-200",
  },
};

export const JobStatusBadge = ({ status }: { status: JobStatus }) => {
  const config = statusConfig[status];
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${config.className}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          status === "active"
            ? "bg-green-500"
            : status === "paused"
              ? "bg-amber-500"
              : status === "closed"
                ? "bg-gray-400"
                : "bg-blue-500"
        }`}
      />
      {config.label}
    </span>
  );
};
