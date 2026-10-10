export type ApplicationStatus =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected"
  | "withdrawn";

export type ApplicationRejectionReason =
  | "not_qualified"
  | "better_matched_candidate"
  | "failed_assessment"
  | "compensation_mismatch"
  | "role_closed"
  | "other";

export interface ApplicationCreateRequest {
  candidate_id: string;
  requisition_id: string;
}

export interface ApplicationResponse {
  id: string;
  candidate_id: string;
  requisition_id: string;
  status: ApplicationStatus;
  applied_at: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface ApplicationListResponse {
  items: ApplicationResponse[];
  next_cursor?: string | null;
}

export interface ApplicationPipelineItem {
  id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  requisition_id: string;
  requisition_title: string;
  status: ApplicationStatus;
  applied_at: string;
  version: number;
}

export interface ApplicationPipelineListResponse {
  items: ApplicationPipelineItem[];
  next_cursor?: string | null;
  stage_counts: Record<ApplicationStatus, number>;
}
