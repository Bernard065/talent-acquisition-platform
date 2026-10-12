import type { ApplicationRejectionReason, ApplicationStatus } from "@/types/api";

export const ALLOWED_NEXT_APPLICATION_STAGES: Partial<
  Record<ApplicationStatus, ApplicationStatus[]>
> = {
  applied: ["screening", "rejected"],
  screening: ["interview", "rejected"],
  interview: ["offer", "rejected"],
  offer: ["hired", "rejected"],
};

export const APPLICATION_REJECTION_REASONS: {
  value: ApplicationRejectionReason;
  label: string;
}[] = [
  { value: "not_qualified", label: "Does not meet role requirements" },
  { value: "better_matched_candidate", label: "Another candidate is a stronger match" },
  { value: "failed_assessment", label: "Did not pass an assessment" },
  { value: "compensation_mismatch", label: "Compensation mismatch" },
  { value: "role_closed", label: "Role is closed" },
  { value: "other", label: "Other" },
];
