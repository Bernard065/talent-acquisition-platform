"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  assignOnboardingTask,
  cancelOnboarding,
  completeOnboarding,
  createOnboardingTemplate,
  getApplicationOnboarding,
  listOnboardingTemplates,
  startApplicationOnboarding,
  updateOnboardingTaskStatus,
} from "../services/onboarding";
import type {
  AssignOnboardingTaskRequest,
  CreateOnboardingTemplateRequest,
  ExpectedInstanceVersionRequest,
  StartOnboardingRequest,
  UpdateOnboardingTaskStatusRequest,
} from "@/types/api/onboarding";

export const onboardingQueryKeys = {
  all: ["onboarding"] as const,
  templates: () => [...onboardingQueryKeys.all, "templates"] as const,
  application: (applicationId: string) =>
    [...onboardingQueryKeys.all, "application", applicationId] as const,
};

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
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.application(applicationId),
      });
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
    onSuccess: async (_task, { applicationId }) => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.application(applicationId),
      });
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
    onSuccess: async (_task, { applicationId }) => {
      await queryClient.invalidateQueries({
        queryKey: onboardingQueryKeys.application(applicationId),
      });
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
    },
  });
}
