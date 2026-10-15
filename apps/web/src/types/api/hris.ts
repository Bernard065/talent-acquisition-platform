export type HrisConnectionStatus = "active" | "disabled";
export type HrisHandoffStatus =
  | "pending"
  | "processing"
  | "succeeded"
  | "retryable_failed"
  | "failed";

export interface HrisConnectionResponse {
  id: string;
  name: string;
  provider: "bamboohr" | "hibob" | "workday" | "custom";
  status: HrisConnectionStatus;
  version: number;
  created_at: string;
  updated_at: string;
  disabled_at: string | null;
}

export interface HrisConnectionListResponse {
  items: HrisConnectionResponse[];
}

export interface CreateHrisConnectionRequest {
  name: string;
  provider: "bamboohr";
  credentials: {
    api_key: string;
    company_domain: string;
  };
}

export interface HrisHandoffOperationResponse {
  id: string;
  provider: "bamboohr" | "hibob" | "workday" | "custom";
  status: HrisHandoffStatus;
  version: number;
  attempt_count: number;
  last_error_code: string | null;
  last_attempt_at: string | null;
  succeeded_at: string | null;
  external_employee_reference: string | null;
  created_at: string;
  updated_at: string;
}

export interface HrisHandoffOperationListResponse {
  items: HrisHandoffOperationResponse[];
  next_cursor: string | null;
}
