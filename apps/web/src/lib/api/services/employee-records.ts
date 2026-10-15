import { get, patch, post, type RequestOptions } from "../client";
import type {
  CreateEmployeeRecordRequest,
  EmployeeRecordResponse,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";

export function getApplicationEmployeeRecord(
  applicationId: string,
  options?: RequestOptions,
) {
  return get<EmployeeRecordResponse | null>(
    `/applications/${applicationId}/employee-record`,
    options,
  );
}

export function createApplicationEmployeeRecord(
  applicationId: string,
  request: CreateEmployeeRecordRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<EmployeeRecordResponse>(
    `/applications/${applicationId}/employee-record`,
    request,
    { ...options, idempotencyKey },
  );
}

export function updateEmployeeRecord(
  employeeId: string,
  request: UpdateEmployeeRecordRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return patch<EmployeeRecordResponse>(
    `/employee-records/${employeeId}`,
    request,
    { ...options, idempotencyKey },
  );
}
