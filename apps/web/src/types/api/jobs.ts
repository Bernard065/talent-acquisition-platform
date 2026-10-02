export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "temporary"
  | "internship";

export type JobPostingStatus = "draft" | "published" | "unpublished" | "expired";

export interface CreateJobPostingRequest {
  employment_type: EmploymentType;
  expires_at?: string | null;
}

export interface ExpectedJobPostingVersionRequest {
  expected_version: number;
}

export interface JobPostingResponse {
  id: string;
  requisition_id: string;
  public_id: string;
  slug: string;
  title: string;
  description: string;
  department: string | null;
  location: string | null;
  employment_type: EmploymentType;
  status: JobPostingStatus;
  published_at: string | null;
  unpublished_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface JobPostingListResponse {
  items: JobPostingResponse[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------------------
// Public Jobs
// ---------------------------------------------------------------------------

export interface PublicJobSummaryResponse {
  public_id: string;
  slug: string;
  title: string;
  department: string | null;
  location: string | null;
  employment_type: EmploymentType;
  published_at: string;
  expires_at: string | null;
}

export interface PublicJobDetailResponse extends PublicJobSummaryResponse {
  description: string | null;
}

export interface PublicJobListResponse {
  items: PublicJobSummaryResponse[];
  next_cursor?: string | null;
}
