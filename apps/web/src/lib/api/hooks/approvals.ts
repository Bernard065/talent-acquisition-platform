"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  approveRequisitionApproval,
  createApprovalPolicy,
  getAssignedRequisitionApproval,
  getApprovalPolicyConfiguration,
  listAssignedRequisitionApprovals,
  rejectRequisitionApproval,
  updateApprovalPolicyApprovers,
} from "../services/approvals";
import type {
  ApprovalPolicyApproversUpdateRequest,
  ApprovalPolicyCreateRequest,
  ApprovalDecisionRequest,
} from "@/types/api/approvals";
import { requisitionQueryKeys } from "./requisitions";

export const approvalQueryKeys = {
  all: ["approvals"] as const,
  configuration: () => [...approvalQueryKeys.all, "configuration"] as const,
  inbox: () => [...approvalQueryKeys.all, "inbox"] as const,
  detail: (approvalId: string) => [...approvalQueryKeys.all, "detail", approvalId] as const,
};

export function useAssignedRequisitionApprovals() {
  const { status } = useSession();

  return useQuery({
    queryKey: approvalQueryKeys.inbox(),
    queryFn: ({ signal }) => listAssignedRequisitionApprovals({ signal }),
    enabled: status === "authenticated",
  });
}

export function useAssignedRequisitionApproval(approvalId: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: approvalQueryKeys.detail(approvalId),
    queryFn: ({ signal }) => getAssignedRequisitionApproval(approvalId, { signal }),
    enabled: status === "authenticated" && Boolean(approvalId),
  });
}

function useRequisitionApprovalDecision(
  decide: typeof approveRequisitionApproval | typeof rejectRequisitionApproval,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ approvalId, decision, idempotencyKey }: {
      approvalId: string;
      decision: ApprovalDecisionRequest;
      idempotencyKey: string;
    }) => decide(approvalId, decision, idempotencyKey),
    onSuccess: async (_result, { approvalId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: approvalQueryKeys.inbox() }),
        queryClient.invalidateQueries({ queryKey: approvalQueryKeys.detail(approvalId) }),
        queryClient.invalidateQueries({ queryKey: requisitionQueryKeys.lists() }),
      ]);
    },
  });
}

export function useApproveRequisitionApproval() {
  return useRequisitionApprovalDecision(approveRequisitionApproval);
}

export function useRejectRequisitionApproval() {
  return useRequisitionApprovalDecision(rejectRequisitionApproval);
}

export function useApprovalPolicyConfiguration() {
  const { status } = useSession();

  return useQuery({
    queryKey: approvalQueryKeys.configuration(),
    queryFn: ({ signal }) => getApprovalPolicyConfiguration({ signal }),
    enabled: status === "authenticated",
  });
}

export function useCreateApprovalPolicy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ policy, idempotencyKey }: {
      policy: ApprovalPolicyCreateRequest;
      idempotencyKey: string;
    }) => createApprovalPolicy(policy, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: approvalQueryKeys.configuration(),
      });
    },
  });
}

export function useUpdateApprovalPolicyApprovers() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ policyId, approvers, idempotencyKey }: {
      policyId: string;
      approvers: ApprovalPolicyApproversUpdateRequest;
      idempotencyKey: string;
    }) => updateApprovalPolicyApprovers(policyId, approvers, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: approvalQueryKeys.configuration(),
      });
    },
  });
}
