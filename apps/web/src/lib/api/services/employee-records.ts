import { get, patch, post, put, type RequestOptions } from "../client";
import type {
  CreateEmployeeRecordRequest,
  CancelEmployeeOffboardingRequest,
  EmployeeDirectoryFilterOptionsResponse,
  EmployeeDirectoryResponse,
  EmployeeRecordResponse,
  LinkEmployeeAccountRequest,
  LinkEmployeeAccountResponse,
  StartEmployeeOffboardingRequest,
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

export function startEmployeeOffboarding(
  employeeId: string,
  request: StartEmployeeOffboardingRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<EmployeeRecordResponse>(
    `/employee-records/${employeeId}/offboarding`,
    request,
    { ...options, idempotencyKey },
  );
}

export function cancelEmployeeOffboarding(
  employeeId: string,
  request: CancelEmployeeOffboardingRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return post<EmployeeRecordResponse>(
    `/employee-records/${employeeId}/offboarding/cancel`,
    request,
    { ...options, idempotencyKey },
  );
}

export function linkEmployeeAccount(
  employeeId: string,
  request: LinkEmployeeAccountRequest,
  idempotencyKey: string,
  options?: RequestOptions,
) {
  return put<LinkEmployeeAccountResponse>(
    `/employee-records/${employeeId}/account`,
    request,
    { ...options, idempotencyKey },
  );
}
