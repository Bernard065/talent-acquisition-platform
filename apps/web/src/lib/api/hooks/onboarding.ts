"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { notificationQueryKeys } from "@/lib/api/hooks/notifications";
import { employeeRecordQueryKeys } from "@/lib/api/hooks/employee-records";
import {
  assignOnboardingTask,
  cancelOnboarding,
  completeOnboarding,
  createOnboardingTemplate,
  createOnboardingTemplateVersion,
  discardOnboardingTemplateDraft,
  getApplicationOnboarding,
  getEmployeePortalOnboarding,
  getOnboardingTaskActivity,
  getOnboardingTaskDocumentDownloadAuthorization,
  getOnboardingTaskDocumentPreviewAuthorization,
  listOnboardingOverview,
  listOnboardingDocumentReviewQueue,
  listOnboardingTaskWorklist,
  listOnboardingTemplates,
  listOnboardingTemplateVersions,
  publishOnboardingTemplateDraft,
  startApplicationOnboarding,
  updateOnboardingTaskDueDate,
  updateOnboardingTemplateDraft,
  updateEmployeePortalTaskStatus,
  updateOnboardingTaskStatus,
  uploadEmployeeOnboardingTaskDocument,
  reviewOnboardingTaskDocument,
} from "../services/onboarding";
import type {
  AssignOnboardingTaskRequest,
  CreateOnboardingTemplateRequest,
  CreateOnboardingTemplateVersionRequest,
  OnboardingTemplateDraftActionRequest,
  ExpectedInstanceVersionRequest,
  StartOnboardingRequest,
  UpdateOnboardingTaskDueDateRequest,
  UpdateEmployeePortalTaskStatusRequest,
  UpdateOnboardingTaskStatusRequest,
  UpdateOnboardingTemplateDraftRequest,
  ReviewOnboardingTaskDocumentRequest,
} from "@/types/api/onboarding";
import type {
  OnboardingOverviewParams,
  OnboardingTaskWorklistParams,
  OnboardingDocumentReviewQueueParams,
} from "../services/onboarding";

export const onboardingQueryKeys = {
  all: ["onboarding"] as const,
  templates: () => [...onboardingQueryKeys.all, "templates"] as const,
  templateVersions: () => [...onboardingQueryKeys.templates(), "versions"] as const,
  overview: () => [...onboardingQueryKeys.all, "overview"] as const,
  overviewList: (params: OnboardingOverviewParams) =>
    [...onboardingQueryKeys.overview(), params] as const,
  taskWorklist: () => [...onboardingQueryKeys.all, "task-worklist"] as const,
  taskWorklistList: (params: OnboardingTaskWorklistParams) =>
    [...onboardingQueryKeys.taskWorklist(), params] as const,
  documentReviewQueue: () =>
    [...onboardingQueryKeys.all, "document-review-queue"] as const,
  documentReviewQueueList: (params: OnboardingDocumentReviewQueueParams) =>
    [...onboardingQueryKeys.documentReviewQueue(), params] as const,
  application: (applicationId: string) =>
    [...onboardingQueryKeys.all, "application", applicationId] as const,
  taskActivity: (taskId: string) =>
    [...onboardingQueryKeys.all, "task-activity", taskId] as const,
  employeePortal: () => [...onboardingQueryKeys.all, "employee-portal"] as const,
};

export function useOnboardingDocumentReviewQueue(
  params: OnboardingDocumentReviewQueueParams,
  enabled = true,
) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.documentReviewQueueList(params),
    queryFn: ({ signal }) => listOnboardingDocumentReviewQueue(params, { signal }),
    enabled: status === "authenticated" && enabled,
    refetchInterval: 30_000,
  });
}

export function useOnboardingOverview(
  params: OnboardingOverviewParams,
  enabled = true,
) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.overviewList(params),
    queryFn: ({ signal }) => listOnboardingOverview(params, { signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useOnboardingTaskWorklist(
  params: OnboardingTaskWorklistParams,
  enabled = true,
) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.taskWorklistList(params),
    queryFn: ({ signal }) => listOnboardingTaskWorklist(params, { signal }),
    enabled: status === "authenticated" && enabled,
    refetchInterval: (query) =>
      query.state.data?.items.some((item) =>
        item.task.documents.some((document) =>
          document.status === "uploaded" || document.status === "scanning",
        ),
      )
        ? 2_000
        : false,
  });
}

export function useOnboardingTemplates(enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.templates(),
    queryFn: ({ signal }) => listOnboardingTemplates({ signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useOnboardingTemplateVersions(enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.templateVersions(),
    queryFn: ({ signal }) => listOnboardingTemplateVersions({ signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useApplicationOnboarding(applicationId: string, enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.application(applicationId),
    queryFn: ({ signal }) => getApplicationOnboarding(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
    refetchInterval: (query) =>
      query.state.data?.tasks.some((task) =>
        task.documents.some((document) =>
          document.status === "uploaded" || document.status === "scanning",
        ),
      )
        ? 2_000
        : false,
  });
}

export function useOnboardingTaskActivity(taskId: string, enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.taskActivity(taskId),
    queryFn: ({ signal }) => getOnboardingTaskActivity(taskId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(taskId),
  });
}

export function useEmployeePortalOnboarding(enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.employeePortal(),
    queryFn: ({ signal }) => getEmployeePortalOnboarding({ signal }),
    enabled: status === "authenticated" && enabled,
    refetchInterval: (query) =>
      query.state.data?.tasks.some((task) =>
        task.documents.some((document) =>
          document.status === "uploaded" ||
          document.status === "scanning",
        ),
      )
        ? 2_000
        : false,
  });
}

export function useUploadEmployeeOnboardingTaskDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, file, replacesDocumentId }: {
      taskId: string;
      file: File;
      replacesDocumentId?: string;
    }) => uploadEmployeeOnboardingTaskDocument(taskId, file, replacesDocumentId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.employeePortal(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
      ]);
    },
    onError: async () => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.employeePortal(),
      });
    },
  });
}

export function useOnboardingTaskDocumentDownload() {
  return useMutation({
    mutationFn: (documentId: string) =>
      getOnboardingTaskDocumentDownloadAuthorization(documentId),
  });
}

export function useOnboardingTaskDocumentPreview() {
  return useMutation({
    mutationFn: (documentId: string) =>
      getOnboardingTaskDocumentPreviewAuthorization(documentId),
  });
}

export function useReviewOnboardingTaskDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, request, idempotencyKey }: {
      documentId: string;
      request: ReviewOnboardingTaskDocumentRequest;
      idempotencyKey: string;
    }) => reviewOnboardingTaskDocument(documentId, request, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.all,
      });
    },
  });
}

export function useUpdateEmployeePortalTaskStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, request, idempotencyKey }: {
      taskId: string;
      request: UpdateEmployeePortalTaskStatusRequest;
      idempotencyKey: string;
    }) => updateEmployeePortalTaskStatus(taskId, request, idempotencyKey),
    onSuccess: async (_task, { taskId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.employeePortal(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskActivity(taskId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
        queryClient.invalidateQueries({
          queryKey: notificationQueryKeys.actionItems,
        }),
      ]);
    },
    onError: async () => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.employeePortal(),
      });
    },
  });
}

export function useCreateOnboardingTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ request, idempotencyKey }: {
      request: CreateOnboardingTemplateRequest;
      idempotencyKey: string;
    }) => createOnboardingTemplate(request, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templates() }),
        queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templateVersions() }),
      ]);
    },
  });
}

export function useCreateOnboardingTemplateVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, request, idempotencyKey }: {
      templateId: string;
      request: CreateOnboardingTemplateVersionRequest;
      idempotencyKey: string;
    }) => createOnboardingTemplateVersion(templateId, request, idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templates() }),
        queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templateVersions() }),
      ]);
    },
  });
}

function invalidateOnboardingTemplateQueries(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templates() }),
    queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templateVersions() }),
  ]);
}

export function useUpdateOnboardingTemplateDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, request, idempotencyKey }: {
      templateId: string;
      request: UpdateOnboardingTemplateDraftRequest;
      idempotencyKey: string;
    }) => updateOnboardingTemplateDraft(templateId, request, idempotencyKey),
    onSuccess: () => invalidateOnboardingTemplateQueries(queryClient),
  });
}

export function usePublishOnboardingTemplateDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, request, idempotencyKey }: {
      templateId: string;
      request: OnboardingTemplateDraftActionRequest;
      idempotencyKey: string;
    }) => publishOnboardingTemplateDraft(templateId, request, idempotencyKey),
    onSuccess: () => invalidateOnboardingTemplateQueries(queryClient),
  });
}

export function useDiscardOnboardingTemplateDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, request, idempotencyKey }: {
      templateId: string;
      request: OnboardingTemplateDraftActionRequest;
      idempotencyKey: string;
    }) => discardOnboardingTemplateDraft(templateId, request, idempotencyKey),
    onSuccess: () => invalidateOnboardingTemplateQueries(queryClient),
  });
}

export function useStartApplicationOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, request, idempotencyKey }: {
      applicationId: string;
      request: StartOnboardingRequest;
      idempotencyKey: string;
    }) => startApplicationOnboarding(applicationId, request, idempotencyKey),
    onSuccess: async (_instance, { applicationId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
        queryClient.invalidateQueries({
          queryKey: notificationQueryKeys.actionItems,
        }),
      ]);
    },
  });
}

export function useAssignOnboardingTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, request, idempotencyKey }: {
      taskId: string;
      request: AssignOnboardingTaskRequest;
      idempotencyKey: string;
      applicationId: string;
    }) => assignOnboardingTask(taskId, request, idempotencyKey),
    onSuccess: async (_task, { applicationId, taskId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskActivity(taskId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
        queryClient.invalidateQueries({
          queryKey: notificationQueryKeys.actionItems,
        }),
      ]);
    },
  });
}

export function useUpdateOnboardingTaskDueDate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, request, idempotencyKey }: {
      taskId: string;
      request: UpdateOnboardingTaskDueDateRequest;
      idempotencyKey: string;
      applicationId: string;
    }) => updateOnboardingTaskDueDate(taskId, request, idempotencyKey),
    onSuccess: async (_task, { applicationId, taskId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskActivity(taskId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
        queryClient.invalidateQueries({
          queryKey: notificationQueryKeys.actionItems,
        }),
      ]);
    },
  });
}

export function useUpdateOnboardingTaskStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, request, idempotencyKey }: {
      taskId: string;
      request: UpdateOnboardingTaskStatusRequest;
      idempotencyKey: string;
      applicationId: string;
    }) => updateOnboardingTaskStatus(taskId, request, idempotencyKey),
    onSuccess: async (_task, { applicationId, taskId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.application(applicationId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskActivity(taskId),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.overview(),
        }),
        queryClient.invalidateQueries({
          queryKey: onboardingQueryKeys.taskWorklist(),
        }),
        queryClient.invalidateQueries({
          queryKey: notificationQueryKeys.actionItems,
        }),
      ]);
    },
  });
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instanceId, request, idempotencyKey }: {
      instanceId: string;
      request: ExpectedInstanceVersionRequest;
      idempotencyKey: string;
      applicationId: string;
    }) => completeOnboarding(instanceId, request, idempotencyKey),
    onSuccess: async (_instance, { applicationId }) => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.application(applicationId),
      });
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.overview(),
      });
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.taskWorklist(),
      });
      await queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.actionItems,
      });
    },
  });
}

export function useCancelOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instanceId, request, idempotencyKey }: {
      instanceId: string;
      request: ExpectedInstanceVersionRequest;
      idempotencyKey: string;
      applicationId: string;
    }) => cancelOnboarding(instanceId, request, idempotencyKey),
    onSuccess: async (_instance, { applicationId }) => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.application(applicationId),
      });
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.overview(),
      });
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.taskWorklist(),
      });
      await queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.actionItems,
      });
    },
  });
}
