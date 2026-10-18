import { get, patch, post, type RequestOptions } from "../client";
import type {
  ApplicationOnboardingResponse,
  AssignOnboardingTaskRequest,
  CreateOnboardingTemplateRequest,
  EmployeePortalOnboardingResponse,
  ExpectedInstanceVersionRequest,
  OnboardingInstanceResponse,
  OnboardingOverviewResponse,
  OnboardingTaskActivityResponse,
  OnboardingTaskResponse,
  OnboardingTaskWorklistResponse,
  OnboardingTaskWorklistView,
  OnboardingTemplateListResponse,
  OnboardingTemplateResponse,
  StartOnboardingRequest,
  UpdateOnboardingTaskDueDateRequest,
  UpdateEmployeePortalTaskStatusRequest,
  UpdateOnboardingTaskStatusRequest,
} from "@/types/api/onboarding";

type OnboardingTemplateCreated = Pick<
  OnboardingTemplateResponse,
  "id" | "name" | "version" | "is_active" | "created_at"
>;

export interface OnboardingOverviewParams {
  page?: number;
  limit?: number;
  query?: string;
  status?: OnboardingInstanceResponse["status"];
  overdue_only?: boolean;
}

export interface OnboardingTaskWorklistParams {
  page?: number;
  limit?: number;
  view?: OnboardingTaskWorklistView;
  query?: string;
  assignee_user_id?: string;
  unassigned_only?: boolean;
}

export function listOnboardingTemplates(options?: RequestOptions) {
  return get<OnboardingTemplateListResponse>("/onboarding-templates", options);
}

export function listOnboardingOverview(
  params: OnboardingOverviewParams = {},
  options?: RequestOptions,
) {
  return get<OnboardingOverviewResponse>("/onboarding-instances", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export function listOnboardingTaskWorklist(
  params: OnboardingTaskWorklistParams = {},
  options?: RequestOptions,
) {
  return get<OnboardingTaskWorklistResponse>("/onboarding-tasks", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export function getApplicationOnboarding(
  applicationId: string,
  options?: RequestOptions,
) {
  return get<ApplicationOnboardingResponse>(
    `/applications/${applicationId}/onboarding`,
    options,
  );
}

export function getOnboardingTaskActivity(
  taskId: string,
  options?: RequestOptions,
) {
  return get<OnboardingTaskActivityResponse>(
    `/onboarding-tasks/${taskId}/activity`,
    options,
  );
}

export function getEmployeePortalOnboarding(options?: RequestOptions) {
  return get<EmployeePortalOnboardingResponse>(
    "/employee-portal/me/onboarding",
    options,
  );
}

export function createOnboardingTemplate(
  request: CreateOnboardingTemplateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingTemplateCreated>("/onboarding-templates", request, {
    ...options,
    idempotencyKey,
  });
}

export function startApplicationOnboarding(
  applicationId: string,
  request: StartOnboardingRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingInstanceResponse>(
    `/applications/${applicationId}/onboarding-instances`,
    request,
    { ...options, idempotencyKey },
  );
}

export function assignOnboardingTask(
  taskId: string,
  request: AssignOnboardingTaskRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingTaskResponse>(
    `/onboarding-tasks/${taskId}/assignee`,
    request,
    { ...options, idempotencyKey },
  );
}

export function updateOnboardingTaskDueDate(
  taskId: string,
  request: UpdateOnboardingTaskDueDateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return patch<OnboardingTaskResponse>(
    `/onboarding-tasks/${taskId}/due-date`,
    request,
    { ...options, idempotencyKey },
  );
}

export function updateOnboardingTaskStatus(
  taskId: string,
  request: UpdateOnboardingTaskStatusRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return patch<OnboardingTaskResponse>(
    `/onboarding-tasks/${taskId}/status`,
    request,
    { ...options, idempotencyKey },
  );
}

export function updateEmployeePortalTaskStatus(
  taskId: string,
  request: UpdateEmployeePortalTaskStatusRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return patch<EmployeePortalOnboardingResponse["tasks"][number]>(
    `/employee-portal/me/onboarding/tasks/${taskId}/status`,
    request,
    { ...options, idempotencyKey },
  );
}

export function completeOnboarding(
  instanceId: string,
  request: ExpectedInstanceVersionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingInstanceResponse>(
    `/onboarding-instances/${instanceId}/complete`,
    request,
    { ...options, idempotencyKey },
  );
}

export function cancelOnboarding(
  instanceId: string,
  request: ExpectedInstanceVersionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingInstanceResponse>(
    `/onboarding-instances/${instanceId}/cancel`,
    request,
    { ...options, idempotencyKey },
  );
}
