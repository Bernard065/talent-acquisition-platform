import { get, patch, post, type RequestOptions } from "../client";
import type {
  ApplicationOnboardingResponse,
  AssignOnboardingTaskRequest,
  CreateOnboardingTaskDocumentRequest,
  CreateOnboardingTemplateRequest,
  EmployeePortalOnboardingResponse,
  ExpectedInstanceVersionRequest,
  OnboardingInstanceResponse,
  OnboardingOverviewResponse,
  OnboardingDocumentReviewQueueResponse,
  OnboardingTaskActivityResponse,
  OnboardingTaskDocumentDownloadAuthorizationResponse,
  OnboardingTaskDocumentResponse,
  OnboardingTaskDocumentUploadAuthorizationResponse,
  ReviewOnboardingTaskDocumentRequest,
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

export interface OnboardingDocumentReviewQueueParams {
  page?: number;
  limit?: number;
  query?: string;
  document_id?: string;
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

export function listOnboardingDocumentReviewQueue(
  params: OnboardingDocumentReviewQueueParams = {},
  options?: RequestOptions,
) {
  return get<OnboardingDocumentReviewQueueResponse>(
    "/onboarding-document-review-queue",
    {
      ...options,
      params: { ...options?.params, ...params },
    },
  );
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

export async function uploadEmployeeOnboardingTaskDocument(
  taskId: string,
  file: File,
): Promise<OnboardingTaskDocumentResponse> {
  const extension = file.name.toLowerCase().split(".").at(-1);
  const extensionContentType = extension === "pdf"
    ? "application/pdf"
    : extension === "docx"
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "";
  const contentType = file.type === "application/pdf" ||
    file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ? file.type
    : extensionContentType;
  if (
    contentType !== "application/pdf" &&
    contentType !== "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    throw new Error("Choose a PDF or DOCX file.");
  }
  if (file.size < 1 || file.size > 10 * 1024 * 1024) {
    throw new Error("The file must be smaller than 10 MB.");
  }

  const checksumBuffer = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const checksumSha256 = Array.from(new Uint8Array(checksumBuffer))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  const request: CreateOnboardingTaskDocumentRequest = {
    original_filename: file.name,
    declared_content_type: contentType,
    expected_byte_size: file.size,
    checksum_sha256: checksumSha256,
  };
  const document = await post<OnboardingTaskDocumentResponse>(
    `/employee-portal/me/onboarding/tasks/${taskId}/documents`,
    request,
    { idempotencyKey: crypto.randomUUID() },
  );
  const authorization = await post<OnboardingTaskDocumentUploadAuthorizationResponse>(
    `/onboarding-task-documents/${document.id}/upload-authorizations`,
    {},
  );
  const uploadResponse = await fetch(authorization.upload_url, {
    method: "PUT",
    headers: authorization.required_headers,
    body: file,
  });
  if (!uploadResponse.ok) {
    throw new Error("The file could not be uploaded. Please try again.");
  }
  return post<OnboardingTaskDocumentResponse>(
    `/onboarding-task-documents/${document.id}/confirm-upload`,
    {},
    { idempotencyKey: crypto.randomUUID() },
  );
}

export function getOnboardingTaskDocumentDownloadAuthorization(
  documentId: string,
  signal?: AbortSignal,
) {
  return get<OnboardingTaskDocumentDownloadAuthorizationResponse>(
    `/onboarding-task-documents/${documentId}/download-authorizations`,
    { signal },
  );
}

export function getOnboardingTaskDocumentPreviewAuthorization(
  documentId: string,
  signal?: AbortSignal,
) {
  return get<OnboardingTaskDocumentDownloadAuthorizationResponse>(
    `/onboarding-task-documents/${documentId}/preview-authorizations`,
    { signal },
  );
}

export function reviewOnboardingTaskDocument(
  documentId: string,
  request: ReviewOnboardingTaskDocumentRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<OnboardingTaskDocumentResponse>(
    `/onboarding-task-documents/${documentId}/reviews`,
    request,
    { ...options, idempotencyKey },
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
