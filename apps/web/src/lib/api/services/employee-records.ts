import { get, patch, post, type RequestOptions } from "../client";
import type {
  CreateEmployeeRecordRequest,
  EmployeeDirectoryFilterOptionsResponse,
  EmployeeDirectoryResponse,
  EmployeeRecordResponse,
  UpdateEmployeeRecordRequest,
} from "@/types/api/employee-records";

export interface EmployeeDirectoryParams {
  page?: number;
  limit?: number;
  query?: string;
  status?: EmployeeRecordResponse["status"];
  department?: string;
  location?: string;
}

export function listEmployeeRecords(
  params: EmployeeDirectoryParams = {},
  options?: RequestOptions,
) {
  return get<EmployeeDirectoryResponse>("/employee-records", {
    ...options,
    params: { ...options?.params, ...params },
  });
}

export function getEmployeeDirectoryFilterOptions(options?: RequestOptions) {
  return get<EmployeeDirectoryFilterOptionsResponse>(
    "/employee-records/filter-options",
    options,
  );
}

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
