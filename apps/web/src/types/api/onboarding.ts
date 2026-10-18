import type { Role } from "./auth";
import type { EmployeeStatus } from "./employee-records";

export type OnboardingInstanceStatus = "active" | "completed" | "cancelled";
export type OnboardingTaskStatus =
  | "not_started"
  | "in_progress"
  | "completed"
  | "blocked"
  | "cancelled";
export type OnboardingTaskResponsibility = "workspace" | "employee";
export type OnboardingTaskEventType =
  | "created"
  | "assigned"
  | "due_date_changed"
  | "status_changed"
  | "completed"
  | "blocked"
  | "cancelled";

export interface OnboardingTemplateTaskRequest {
  title: string;
  description: string | null;
  due_offset_days: number | null;
  default_assignee_role: Role | null;
  responsible_party: OnboardingTaskResponsibility;
}

export interface CreateOnboardingTemplateRequest {
  name: string;
  version: number;
  tasks: OnboardingTemplateTaskRequest[];
}

export interface OnboardingTemplateTaskResponse extends OnboardingTemplateTaskRequest {
  id: string;
  position: number;
}

export interface OnboardingTemplateResponse {
  id: string;
  name: string;
  version: number;
  is_active: boolean;
  created_at: string;
  tasks: OnboardingTemplateTaskResponse[];
}

export interface OnboardingTemplateListResponse {
  items: OnboardingTemplateResponse[];
}

export interface OnboardingTaskResponse {
  id: string;
  onboarding_instance_id: string;
  template_task_id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  assignee_user_id: string | null;
  responsible_party: OnboardingTaskResponsibility;
  status: OnboardingTaskStatus;
  blocked_reason: string | null;
  resolution_note: string | null;
  completed_at: string | null;
  version: number;
}

export interface OnboardingTaskActivityItem {
  id: string;
  event_type: OnboardingTaskEventType;
  from_status: OnboardingTaskStatus | null;
  to_status: OnboardingTaskStatus;
  note: string | null;
  actor_display_name: string;
  occurred_at: string;
}

export interface OnboardingTaskActivityResponse {
  items: OnboardingTaskActivityItem[];
}

export interface OnboardingInstanceResponse {
  id: string;
  application_id: string;
  onboarding_template_id: string;
  status: OnboardingInstanceStatus;
  started_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  version: number;
}

export interface ApplicationOnboardingResponse {
  instance: OnboardingInstanceResponse | null;
  tasks: OnboardingTaskResponse[];
}

export interface OnboardingOverviewItemResponse {
  instance: OnboardingInstanceResponse;
  employee_name: string;
  job_title: string;
  total_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
}

export interface OnboardingOverviewResponse {
  items: OnboardingOverviewItemResponse[];
  total: number;
  page: number;
  limit: number;
  active_plan_count: number;
  overdue_task_count: number;
}

export interface EmployeePortalTaskResponse {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  responsible_party: OnboardingTaskResponsibility;
  status: OnboardingTaskStatus;
  blocked_reason: string | null;
  resolution_note: string | null;
  completed_at: string | null;
  version: number;
  can_update: boolean;
}

export interface EmployeePortalOnboardingResponse {
  profile: {
    full_name: string;
    work_email: string | null;
    start_date: string | null;
    job_title: string;
    department: string | null;
    location: string | null;
    status: EmployeeStatus;
  };
  onboarding_status: OnboardingInstanceStatus | null;
  started_at: string | null;
  completed_at: string | null;
  tasks: EmployeePortalTaskResponse[];
}

export interface StartOnboardingRequest {
  onboarding_template_id: string;
}

export interface AssignOnboardingTaskRequest {
  assignee_user_id: string | null;
  expected_task_version: number;
}

export interface UpdateOnboardingTaskDueDateRequest {
  due_date: string | null;
  expected_task_version: number;
}

export interface UpdateOnboardingTaskStatusRequest {
  expected_version: number;
  target_status: OnboardingTaskStatus;
  blocked_reason?: string | null;
  resolution_note?: string | null;
}

export interface UpdateEmployeePortalTaskStatusRequest {
  expected_version: number;
  target_status: "in_progress" | "completed" | "blocked";
  blocked_reason?: string | null;
}

export interface ExpectedInstanceVersionRequest {
  expected_instance_version: number;
}
