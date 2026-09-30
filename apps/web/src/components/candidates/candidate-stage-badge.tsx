import type { CandidateStage } from "@/lib/mock-candidates";

const stageConfig: Record<CandidateStage, { label: string; className: string }> = {
  new: {
    label: "New",
    className: "bg-blue-50 text-blue-700 border-blue-200",
  },
  screening: {
    label: "Screening",
    className: "bg-purple-50 text-purple-700 border-purple-200",
  },
  interview: {
    label: "Interview",
    className: "bg-amber-50 text-amber-700 border-amber-200",
  },
  offer: {
    label: "Offer",
    className: "bg-green-50 text-green-700 border-green-200",
  },
  hired: {
    label: "Hired",
    className: "bg-emerald-100 text-emerald-800 border-emerald-300",
  },
  rejected: {
    label: "Rejected",
    className: "bg-gray-100 text-gray-600 border-gray-200",
  },
};

export const CandidateStageBadge = ({ stage }: { stage: CandidateStage }) => {
  const config = stageConfig[stage];
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${config.className}`}
    >
      {config.label}
    </span>
  );
};
