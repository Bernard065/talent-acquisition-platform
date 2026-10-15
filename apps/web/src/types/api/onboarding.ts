import type { Role } from "./auth";

export type OnboardingInstanceStatus = "active" | "completed" | "cancelled";
export type OnboardingTaskStatus =
  | "not_started"
  | "in_progress"
  | "completed"
  | "blocked"
  | "cancelled";

export interface OnboardingTemplateTaskRequest {
  title: string;
  description: string | null;
  due_offset_days: number | null;
  default_assignee_role: Role | null;
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
  status: OnboardingTaskStatus;
  completed_at: string | null;
  blocked_reason: string | null;
  version: number;
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

export interface StartOnboardingRequest {
  onboarding_template_id: string;
}

export interface AssignOnboardingTaskRequest {
  assignee_user_id: string;
  expected_task_version: number;
}

export interface UpdateOnboardingTaskStatusRequest {
  expected_version: number;
  target_status: OnboardingTaskStatus;
  blocked_reason?: string | null;
}

export interface ExpectedInstanceVersionRequest {
  expected_instance_version: number;
}
