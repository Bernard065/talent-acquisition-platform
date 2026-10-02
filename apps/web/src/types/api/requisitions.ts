export type RequisitionStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "open"
  | "on_hold"
  | "closed"
  | "cancelled";

export interface RequisitionCreateRequest {
  title: string;
  description?: string | null;
  department?: string | null;
  location?: string | null;
  headcount?: number; 
}

export interface RequisitionUpdateRequest {
  title?: string | null;
  description?: string | null;
  department?: string | null;
  location?: string | null;
  headcount?: number | null;
}

export interface RequisitionTransitionRequest {
  target_status: RequisitionStatus;
}

export interface RequisitionResponse {
  id: string;
  title: string;
  description: string | null;
  department: string | null;
  location: string | null;
  headcount: number;
  status: RequisitionStatus;
  version: number;
  created_by_subject: string;
  created_at: string;
  updated_at: string;
}

export interface RequisitionListResponse {
  items: RequisitionResponse[];
  next_cursor?: string | null;
}
