export type EmployeeStatus = "preboarding" | "active" | "inactive";

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
  status: EmployeeStatus;
  version: number;
  created_at: string;
  updated_at: string;
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
