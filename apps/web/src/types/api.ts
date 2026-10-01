export interface PublicJobSummary {
  public_id: string;
  slug: string;
  title: string;
  department: string | null;
  location: string | null;
  employment_type: "FULL_TIME" | "PART_TIME" | "CONTRACT" | "INTERNSHIP";
  published_at: string;
  expires_at: string | null;
}

export interface PublicJobDetail extends PublicJobSummary {
  description: string | null;
}

export interface PublicJobListResponse {
  items: PublicJobSummary[];
  next_cursor: string | null;
}
