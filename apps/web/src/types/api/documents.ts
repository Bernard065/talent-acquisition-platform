export type CandidateDocumentStatus =
  | "pending_upload"
  | "uploaded"
  | "scanning"
  | "available"
  | "quarantined"
  | "rejected"
  | "deleted";

export interface CandidateDocumentResponse {
  id: string;
  candidate_id: string;
  original_filename: string;
  declared_content_type: string;
  expected_byte_size: number;
  status: CandidateDocumentStatus;
  uploaded_at: string | null;
  scan_started_at: string | null;
  scan_completed_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface CandidateDocumentDownloadAuthorizationResponse {
  url: string;
  expires_at: string;
}
