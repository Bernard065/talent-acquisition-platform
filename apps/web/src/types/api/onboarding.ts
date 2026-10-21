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
export type OnboardingTemplatePublicationStatus = "draft" | "published";
export type OnboardingTaskWorklistView = "open" | "due_soon" | "overdue" | "completed";
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
  requires_document_upload: boolean;
  requires_document_review: boolean;
  prerequisite_task_positions: number[];
}

export interface CreateOnboardingTemplateRequest {
  name: string;
  version: number;
  tasks: OnboardingTemplateTaskRequest[];
}

export interface CreateOnboardingTemplateVersionRequest {
  expected_version: number;
  restore_from_template_id?: string | null;
  tasks: OnboardingTemplateTaskRequest[];
}

export interface UpdateOnboardingTemplateDraftRequest {
  expected_revision: number;
  tasks: OnboardingTemplateTaskRequest[];
}

export interface OnboardingTemplateDraftActionRequest {
  expected_revision: number;
}

export interface OnboardingTemplateDraftDiscardResponse {
  template_id: string;
  discarded: true;
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
  publication_status: OnboardingTemplatePublicationStatus;
  draft_revision: number;
  created_at: string;
  created_by_display_name?: string | null;
  published_at?: string | null;
  published_by_display_name?: string | null;
  based_on_version?: number | null;
  restored_from_version?: number | null;
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
  requires_document_upload: boolean;
  requires_document_review: boolean;
  status: OnboardingTaskStatus;
  blocked_reason: string | null;
  resolution_note: string | null;
  completed_at: string | null;
  version: number;
  prerequisites: OnboardingTaskPrerequisite[];
  documents: OnboardingTaskDocumentResponse[];
}

export interface OnboardingTaskPrerequisite {
  id: string;
  title: string;
  status: OnboardingTaskStatus;
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

export interface OnboardingTaskWorklistItemResponse {
  task: OnboardingTaskResponse;
  application_id: string;
  instance_status: OnboardingInstanceStatus;
  employee_name: string;
  job_title: string;
  assignee_display_name: string | null;
  step_number: number;
  can_update: boolean;
  can_progress: boolean;
}

export interface OnboardingTaskWorklistAssigneeResponse {
  id: string;
  display_name: string;
}

export interface OnboardingTaskWorklistResponse {
  items: OnboardingTaskWorklistItemResponse[];
  assignees: OnboardingTaskWorklistAssigneeResponse[];
  total: number;
  page: number;
  limit: number;
  view: OnboardingTaskWorklistView;
}

export interface OnboardingDocumentReviewQueueItemResponse {
  document: OnboardingTaskDocumentResponse;
  previous_versions: OnboardingTaskDocumentResponse[];
  onboarding_task_id: string;
  onboarding_instance_id: string;
  application_id: string;
  task_title: string;
  employee_name: string;
  job_title: string;
}

export interface OnboardingDocumentReviewQueueResponse {
  items: OnboardingDocumentReviewQueueItemResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface EmployeePortalTaskResponse {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  responsible_party: OnboardingTaskResponsibility;
  requires_document_upload: boolean;
  requires_document_review: boolean;
  status: OnboardingTaskStatus;
  blocked_reason: string | null;
  resolution_note: string | null;
  completed_at: string | null;
  version: number;
  can_update: boolean;
  prerequisites: OnboardingTaskPrerequisite[];
  documents: OnboardingTaskDocumentResponse[];
}

export type OnboardingTaskDocumentStatus =
  | "pending_upload"
  | "uploaded"
  | "scanning"
  | "available"
  | "quarantined"
  | "rejected";

export type OnboardingTaskDocumentReviewStatus =
  | "not_required"
  | "pending_review"
  | "accepted"
  | "changes_requested";

export interface OnboardingTaskDocumentResponse {
  id: string;
  onboarding_task_id: string;
  replaces_document_id: string | null;
  revision_number: number;
  original_filename: string;
  declared_content_type: string;
  expected_byte_size: number;
  status: OnboardingTaskDocumentStatus;
  review_status: OnboardingTaskDocumentReviewStatus;
  review_comment: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  uploaded_at: string | null;
  scan_started_at: string | null;
  scan_completed_at: string | null;
  created_at: string;
  version: number;
}

export interface ReviewOnboardingTaskDocumentRequest {
  expected_document_version: number;
  decision: "accepted" | "changes_requested";
  comment: string | null;
}

export interface CreateOnboardingTaskDocumentRequest {
  original_filename: string;
  declared_content_type:
    | "application/pdf"
    | "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  expected_byte_size: number;
  checksum_sha256: string;
  replaces_document_id?: string;
}

export interface OnboardingTaskDocumentUploadAuthorizationResponse {
  upload_url: string;
  required_headers: Record<string, string>;
  expires_at: string;
}

export interface OnboardingTaskDocumentDownloadAuthorizationResponse {
  url: string;
  expires_at: string;
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
