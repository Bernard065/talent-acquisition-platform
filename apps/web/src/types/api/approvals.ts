export type RequisitionApprovalStatus = "pending" | "approved" | "rejected";
export type ApprovalDecisionStatus = "pending" | "approved" | "rejected";

export interface RequisitionApprovalResponse {
  id: string;
  requisition_id: string;
  approval_policy_id: string;
  status: RequisitionApprovalStatus;
  current_step: number;
  submitted_by_subject: string;
  submitted_at: string;
  completed_at: string | null;
}

export interface RequisitionApprovalReviewResponse {
  approval_id: string;
  requisition_id: string;
  title: string;
  description: string | null;
  department: string | null;
  location: string | null;
  headcount: number;
  requisition_status: string;
  approval_status: RequisitionApprovalStatus;
  current_step: number;
  assigned_step: number;
  assigned_decision_status: ApprovalDecisionStatus;
  is_current_approver: boolean;
  submitted_by_subject: string;
  submitted_at: string;
  completed_at: string | null;
}

export interface RequisitionApprovalInboxResponse {
  items: RequisitionApprovalReviewResponse[];
}

export interface ApprovalDecisionRequest {
  comment?: string | null;
}

export interface ApprovalPolicyResponse {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ApprovalApproverResponse {
  id: string;
  display_name: string;
  email: string;
  is_current_user: boolean;
}

export interface ApprovalPolicyConfigurationResponse {
  default_policy: ApprovalPolicyResponse | null;
  default_approver_user_ids: string[];
  available_approvers: ApprovalApproverResponse[];
}

export interface ApprovalPolicyCreateRequest {
  name: string;
  approver_user_ids: string[];
  is_default: boolean;
}

export interface ApprovalPolicyApproversUpdateRequest {
  approver_user_ids: string[];
}
