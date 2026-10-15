"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import type {
  CreateEmployeeRecordRequest,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";
import type { EmployeeDirectoryParams } from "../services/employee-records";
import {
  createApplicationEmployeeRecord,
  getEmployeeDirectoryFilterOptions,
  getApplicationEmployeeRecord,
  listEmployeeRecords,
  updateEmployeeRecord,
} from "../services/employee-records";

export const employeeRecordQueryKeys = {
  all: ["employee-records"] as const,
  lists: () => [...employeeRecordQueryKeys.all, "list"] as const,
  list: (params: EmployeeDirectoryParams = {}) =>
    [...employeeRecordQueryKeys.lists(), params] as const,
  filterOptions: () => [...employeeRecordQueryKeys.all, "filter-options"] as const,
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
