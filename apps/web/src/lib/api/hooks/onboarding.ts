"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { employeeRecordQueryKeys } from "@/lib/api/hooks/employee-records";
import {
  assignOnboardingTask,
  cancelOnboarding,
  completeOnboarding,
  createOnboardingTemplate,
  getApplicationOnboarding,
  getEmployeePortalOnboarding,
  getOnboardingTaskActivity,
  listOnboardingOverview,
  listOnboardingTemplates,
  startApplicationOnboarding,
  updateOnboardingTaskDueDate,
  updateEmployeePortalTaskStatus,
  updateOnboardingTaskStatus,
} from "../services/onboarding";
import type {
  AssignOnboardingTaskRequest,
  CreateOnboardingTemplateRequest,
  ExpectedInstanceVersionRequest,
  StartOnboardingRequest,
  UpdateOnboardingTaskDueDateRequest,
  UpdateEmployeePortalTaskStatusRequest,
  UpdateOnboardingTaskStatusRequest,
} from "@/types/api/onboarding";
import type { OnboardingOverviewParams } from "../services/onboarding";

export const onboardingQueryKeys = {
  all: ["onboarding"] as const,
  templates: () => [...onboardingQueryKeys.all, "templates"] as const,
  overview: () => [...onboardingQueryKeys.all, "overview"] as const,
  overviewList: (params: OnboardingOverviewParams) =>
    [...onboardingQueryKeys.overview(), params] as const,
  application: (applicationId: string) =>
    [...onboardingQueryKeys.all, "application", applicationId] as const,
  taskActivity: (taskId: string) =>
    [...onboardingQueryKeys.all, "task-activity", taskId] as const,
  employeePortal: () => [...onboardingQueryKeys.all, "employee-portal"] as const,
};

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

export function useOnboardingTemplates(enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.templates(),
    queryFn: ({ signal }) => listOnboardingTemplates({ signal }),
    enabled: status === "authenticated" && enabled,
  });
}

export function useApplicationOnboarding(applicationId: string, enabled = true) {
  const { status } = useSession();
  return useQuery({
    queryKey: onboardingQueryKeys.application(applicationId),
    queryFn: ({ signal }) => getApplicationOnboarding(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
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
      await queryClient.invalidateQueries({ queryKey: onboardingQueryKeys.templates() });
    },
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
    },
  });
}
