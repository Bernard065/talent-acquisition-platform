export type EmployeeStatus = "preboarding" | "active" | "offboarding" | "inactive";
export type EmployeeOffboardingReason =
  | "resignation"
  | "retirement"
  | "redundancy"
  | "contract_end"
  | "termination"
  | "other";

export interface EmployeeRecordResponse {
  id: string;
  application_id: string;
  candidate_id: string;
  employee_number: string | null;
  work_email: string | null;
  start_date: string | null;
  job_title: string;
  department: string | null;
  location: string | null;
  manager_user_id: string | null;
  user_id: string | null;
  status: EmployeeStatus;
  last_working_day: string | null;
  offboarding_reason: EmployeeOffboardingReason | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EmployeeDirectoryItemResponse extends EmployeeRecordResponse {
  employee_name: string;
}

export interface EmployeeDirectoryResponse {
  items: EmployeeDirectoryItemResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface EmployeeDirectoryFilterOptionsResponse {
  departments: string[];
  locations: string[];
}

export interface CreateEmployeeRecordRequest {
  employee_number?: string | null;
  work_email?: string | null;
  start_date?: string | null;
  manager_user_id?: string | null;
}

export interface UpdateEmployeeRecordRequest {
  expected_version: number;
  employee_number?: string | null;
  work_email?: string | null;
  start_date?: string | null;
  job_title?: string;
  department?: string | null;
  location?: string | null;
  manager_user_id?: string | null;
  status?: EmployeeStatus;
}

export interface LinkEmployeeAccountRequest {
  user_id: string | null;
  expected_version: number;
}

export interface StartEmployeeOffboardingRequest {
  expected_version: number;
  last_working_day: string;
  reason: EmployeeOffboardingReason;
}

export interface CancelEmployeeOffboardingRequest {
  expected_version: number;
}

export interface LinkEmployeeAccountResponse {
  employee_id: string;
  user_id: string | null;
  version: number;
}
