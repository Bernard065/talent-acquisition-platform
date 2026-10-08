import { get, patch, post, type RequestOptions } from "../client";
import type {
  ApprovalDecisionRequest,
  ApprovalPolicyConfigurationResponse,
  ApprovalPolicyCreateRequest,
  ApprovalPolicyApproversUpdateRequest,
  ApprovalPolicyResponse,
  RequisitionApprovalResponse,
  RequisitionApprovalInboxResponse,
  RequisitionApprovalReviewResponse,
} from "@/types/api/approvals";

export function listAssignedRequisitionApprovals(
  options?: RequestOptions,
): Promise<RequisitionApprovalInboxResponse> {
  return get<RequisitionApprovalInboxResponse>(
    "/requisition-approvals/inbox",
    options,
  );
}

export function getAssignedRequisitionApproval(
  approvalId: string,
  options?: RequestOptions,
): Promise<RequisitionApprovalReviewResponse> {
  return get<RequisitionApprovalReviewResponse>(
    `/requisition-approvals/${approvalId}`,
    options,
  );
}

export function approveRequisitionApproval(
  approvalId: string,
  request: ApprovalDecisionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionApprovalResponse> {
  return post<RequisitionApprovalResponse>(
    `/requisition-approvals/${approvalId}/approve`,
    request,
    { ...options, idempotencyKey },
  );
}

export function rejectRequisitionApproval(
  approvalId: string,
  request: ApprovalDecisionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionApprovalResponse> {
  return post<RequisitionApprovalResponse>(
    `/requisition-approvals/${approvalId}/reject`,
    request,
    { ...options, idempotencyKey },
  );
}

export function getApprovalPolicyConfiguration(
  options?: RequestOptions,
): Promise<ApprovalPolicyConfigurationResponse> {
  return get<ApprovalPolicyConfigurationResponse>(
    "/approval-policies/configuration",
    options,
  );
}

export function updateApprovalPolicyApprovers(
  policyId: string,
  request: ApprovalPolicyApproversUpdateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApprovalPolicyResponse> {
  return patch<ApprovalPolicyResponse>(
    `/approval-policies/${policyId}/approvers`,
    request,
    { ...options, idempotencyKey },
  );
}

export function createApprovalPolicy(
  request: ApprovalPolicyCreateRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApprovalPolicyResponse> {
  return post<ApprovalPolicyResponse>("/approval-policies", request, {
    ...options,
    idempotencyKey,
  });
}

export function submitRequisitionForApproval(
  requisitionId: string,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<RequisitionApprovalResponse> {
  return post<RequisitionApprovalResponse>(
    `/requisitions/${requisitionId}/approval-submissions`,
    undefined,
    { ...options, idempotencyKey },
  );
}
