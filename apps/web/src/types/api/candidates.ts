export type CandidateConsentStatus = "unknown" | "granted" | "withdrawn";
export type CandidatePrivacyStatus = "active" | "erasure_pending" | "erased";

export interface CandidateCreateRequest {
  full_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  source: string;
  source_metadata?: Record<string, unknown>;
  consent_status?: CandidateConsentStatus;
}

export interface CandidateResponse {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  source: string;
  source_metadata: Record<string, unknown>;
  consent_status: CandidateConsentStatus;
  consent_updated_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface CandidateListResponse {
  items: CandidateResponse[];
  next_cursor?: string | null;
}

export interface CandidateFilterOptionsResponse {
  sources: string[];
  locations: string[];
}

export interface CandidatePrivacyOperationResponse {
  candidate_id: string;
  consent_status: CandidateConsentStatus;
  privacy_status: CandidatePrivacyStatus;
  erasure_requested_at: string | null;
  erased_at: string | null;
}

export type CandidateTalentPoolCaptureMethod =
  | "signed_form"
  | "email_confirmation"
  | "recruiter_recorded";

export type CandidateTalentPoolConsentEventType = "granted" | "renewed" | "withdrawn";

export interface CandidateTalentPoolConsentGrantRequest {
  notice_version: string;
  capture_method: CandidateTalentPoolCaptureMethod;
}

export interface CandidateTalentPoolConsentWithdrawalRequest {
  capture_method: CandidateTalentPoolCaptureMethod;
}

export interface CandidateTalentPoolConsentResponse {
  event_id: string;
  candidate_id: string;
  event_version: number;
  event_type: CandidateTalentPoolConsentEventType;
  capture_method: CandidateTalentPoolCaptureMethod;
  notice_version: string | null;
  recorded_at: string;
}

export interface CandidateTalentPoolConsentState {
  candidate_id: string;
  status: "unknown" | "granted" | "withdrawn";
  event_version: number | null;
  capture_method: CandidateTalentPoolCaptureMethod | null;
  notice_version: string | null;
  recorded_at: string | null;
}
