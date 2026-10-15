"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import type {
  CreateEmployeeRecordRequest,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";
import {
  createApplicationEmployeeRecord,
  getApplicationEmployeeRecord,
  updateEmployeeRecord,
} from "../services/employee-records";

export const employeeRecordQueryKeys = {
  all: ["employee-records"] as const,
  application: (applicationId: string) =>
    [...employeeRecordQueryKeys.all, applicationId] as const,
};

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
      await queryClient.invalidateQueries({
        queryKey: employeeRecordQueryKeys.application(variables.applicationId),
      });
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
      await queryClient.invalidateQueries({
        queryKey: employeeRecordQueryKeys.application(variables.applicationId),
      });
    },
  });
}
