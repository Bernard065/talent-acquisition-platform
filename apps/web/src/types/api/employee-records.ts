export type EmployeeStatus = "preboarding" | "active" | "offboarding" | "inactive";
export type EmployeeOffboardingReason =
  | "resignation"
  | "retirement"
  | "redundancy"
  | "contract_end"
  | "termination"
  | "other";
export type EmployeeOffboardingTaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "blocked";

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

export interface OffboardingTemplateTask {
  id?: string;
  position?: number;
  title: string;
  description: string | null;
  due_days_before_last_working_day: number;
}

export interface OffboardingTemplateResponse {
  items: OffboardingTemplateTask[];
}

export interface ReplaceOffboardingTemplateRequest {
  items: Array<{
    title: string;
    description: string | null;
    due_days_before_last_working_day: number;
  }>;
}

export interface EmployeeOffboardingTaskResponse {
  id: string;
  position: number;
  title: string;
  description: string | null;
  due_date: string;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  status: EmployeeOffboardingTaskStatus;
  completion_notes: string | null;
  completed_at: string | null;
  version: number;
}

export interface EmployeeOffboardingChecklistResponse {
  items: EmployeeOffboardingTaskResponse[];
  completed_count: number;
  total_count: number;
}

export interface EmployeeOffboardingOverviewItemResponse {
  employee_id: string;
  application_id: string;
  employee_name: string;
  job_title: string;
  department: string | null;
  location: string | null;
  last_working_day: string | null;
  reason: EmployeeOffboardingReason | null;
  completed_task_count: number;
  total_task_count: number;
  overdue_task_count: number;
  next_due_date: string | null;
}

export interface EmployeeOffboardingOverviewResponse {
  items: EmployeeOffboardingOverviewItemResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface MyEmployeeOffboardingTaskResponse {
  id: string;
  employee_id: string;
  employee_name: string;
  job_title: string;
  title: string;
  description: string | null;
  due_date: string;
  status: EmployeeOffboardingTaskStatus;
  completion_notes: string | null;
  completed_at: string | null;
  version: number;
}

export interface MyEmployeeOffboardingTasksResponse {
  items: MyEmployeeOffboardingTaskResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface EmployeeOffboardingTaskUpdateRequest {
  expected_version: number;
  assigned_to_user_id?: string | null;
  due_date?: string;
  status?: EmployeeOffboardingTaskStatus;
  completion_notes?: string | null;
}

export interface LinkEmployeeAccountResponse {
  employee_id: string;
  user_id: string | null;
  version: number;
}
