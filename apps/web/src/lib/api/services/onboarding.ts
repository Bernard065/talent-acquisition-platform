import { get, patch, post, type RequestOptions } from "../client";
import type {
  ApplicationOnboardingResponse,
  AssignOnboardingTaskRequest,
  CreateOnboardingTemplateRequest,
  EmployeePortalOnboardingResponse,
  ExpectedInstanceVersionRequest,
  OnboardingInstanceResponse,
  OnboardingOverviewResponse,
  OnboardingTaskResponse,
  OnboardingTemplateListResponse,
  OnboardingTemplateResponse,
  StartOnboardingRequest,
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

export function getApplicationOnboarding(
  applicationId: string,
  options?: RequestOptions,
) {
  return get<ApplicationOnboardingResponse>(
    `/applications/${applicationId}/onboarding`,
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
