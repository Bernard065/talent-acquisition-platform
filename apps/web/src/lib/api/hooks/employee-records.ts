"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import type {
  CancelEmployeeOffboardingRequest,
  CreateEmployeeRecordRequest,
  EmployeeRecordResponse,
  EmployeeOffboardingTaskUpdateRequest,
  LinkEmployeeAccountRequest,
  ReplaceOffboardingTemplateRequest,
  StartEmployeeOffboardingRequest,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";
import type { EmployeeDirectoryParams } from "../services/employee-records";
import {
  cancelEmployeeOffboarding,
  createApplicationEmployeeRecord,
  getEmployeeDirectoryFilterOptions,
  getApplicationEmployeeRecord,
  listEmployeeRecords,
  linkEmployeeAccount,
  getEmployeeOffboardingChecklist,
  getOffboardingTemplate,
  replaceOffboardingTemplate,
  startEmployeeOffboarding,
  updateEmployeeOffboardingTask,
  updateEmployeeRecord,
} from "../services/employee-records";

export const employeeRecordQueryKeys = {
  all: ["employee-records"] as const,
  lists: () => [...employeeRecordQueryKeys.all, "list"] as const,
  list: (params: EmployeeDirectoryParams = {}) =>
    [...employeeRecordQueryKeys.lists(), params] as const,
  filterOptions: () => [...employeeRecordQueryKeys.all, "filter-options"] as const,
  offboardingTemplate: () => [...employeeRecordQueryKeys.all, "offboarding-template"] as const,
  offboardingTasks: (employeeId: string) =>
    [...employeeRecordQueryKeys.all, "offboarding-tasks", employeeId] as const,
  application: (applicationId: string) =>
    [...employeeRecordQueryKeys.all, applicationId] as const,
};

export function useEmployeeDirectory(params: EmployeeDirectoryParams) {
  const { status } = useSession();
  return useQuery({
    queryKey: employeeRecordQueryKeys.list(params),
    queryFn: ({ signal }) => listEmployeeRecords(params, { signal }),
    enabled: status === "authenticated",
  });
}

export function useOffboardingTemplate() {
  const { status } = useSession();
  return useQuery({
    queryKey: employeeRecordQueryKeys.offboardingTemplate(),
    queryFn: ({ signal }) => getOffboardingTemplate({ signal }),
    enabled: status === "authenticated",
  });
}

export function useReplaceOffboardingTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ReplaceOffboardingTemplateRequest) =>
      replaceOffboardingTemplate(request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: employeeRecordQueryKeys.offboardingTemplate(),
      });
    },
  });
}

export function useEmployeeOffboardingChecklist(
  employeeId: string,
  enabled = true,
) {
  const { status } = useSession();
  return useQuery({
    queryKey: employeeRecordQueryKeys.offboardingTasks(employeeId),
    queryFn: ({ signal }) => getEmployeeOffboardingChecklist(employeeId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(employeeId),
  });
}

export function useUpdateEmployeeOffboardingTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, request, idempotencyKey }: {
      taskId: string;
      employeeId: string;
      request: EmployeeOffboardingTaskUpdateRequest;
      idempotencyKey: string;
    }) => updateEmployeeOffboardingTask(taskId, request, idempotencyKey),
    onSuccess: async (_task, variables) => {
      await queryClient.invalidateQueries({
        queryKey: employeeRecordQueryKeys.offboardingTasks(variables.employeeId),
      });
    },
  });
}

export function useEmployeeDirectoryFilterOptions() {
  const { status } = useSession();
  return useQuery({
    queryKey: employeeRecordQueryKeys.filterOptions(),
    queryFn: ({ signal }) => getEmployeeDirectoryFilterOptions({ signal }),
    enabled: status === "authenticated",
  });
}

export function useApplicationEmployeeRecord(
  applicationId: string,
  enabled = true,
) {
  const { status } = useSession();
  return useQuery({
    queryKey: employeeRecordQueryKeys.application(applicationId),
    queryFn: ({ signal }) => getApplicationEmployeeRecord(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
  });
}

export function useCreateApplicationEmployeeRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      applicationId,
      request,
      idempotencyKey,
    }: {
      applicationId: string;
      request: CreateEmployeeRecordRequest;
      idempotencyKey: string;
    }) => createApplicationEmployeeRecord(applicationId, request, idempotencyKey),
    onSuccess: async (_record, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.application(variables.applicationId),
        }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.filterOptions() }),
      ]);
    },
  });
}

export function useUpdateEmployeeRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      request,
      idempotencyKey,
    }: {
      employeeId: string;
      applicationId: string;
      request: UpdateEmployeeRecordRequest;
      idempotencyKey: string;
    }) => updateEmployeeRecord(employeeId, request, idempotencyKey),
    onSuccess: async (_record, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.application(variables.applicationId),
        }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.filterOptions() }),
      ]);
    },
  });
}

interface EmployeeOffboardingMutationVariables<TRequest> {
  employeeId: string;
  applicationId: string;
  request: TRequest;
  idempotencyKey: string;
}

function useEmployeeOffboardingMutation<TRequest>(
  mutationFn: (variables: EmployeeOffboardingMutationVariables<TRequest>) => Promise<EmployeeRecordResponse>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (_employee, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.application(variables.applicationId),
        }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.lists() }),
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.offboardingTasks(variables.employeeId),
        }),
      ]);
    },
  });
}

export function useStartEmployeeOffboarding() {
  return useEmployeeOffboardingMutation<StartEmployeeOffboardingRequest>((variables) =>
    startEmployeeOffboarding(
      variables.employeeId,
      variables.request,
      variables.idempotencyKey,
    ),
  );
}

export function useCancelEmployeeOffboarding() {
  return useEmployeeOffboardingMutation<CancelEmployeeOffboardingRequest>((variables) =>
    cancelEmployeeOffboarding(
      variables.employeeId,
      variables.request,
      variables.idempotencyKey,
    ),
  );
}

export function useLinkEmployeeAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      request,
      idempotencyKey,
    }: {
      employeeId: string;
      applicationId: string;
      request: LinkEmployeeAccountRequest;
      idempotencyKey: string;
    }) => linkEmployeeAccount(employeeId, request, idempotencyKey),
    onSuccess: async (_account, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: employeeRecordQueryKeys.application(variables.applicationId),
        }),
        queryClient.invalidateQueries({ queryKey: employeeRecordQueryKeys.lists() }),
      ]);
    },
  });
}
