export type ApplicationStatus =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected"
  | "withdrawn";

export type ApplicationRejectionReason =
  | "not_qualified"
  | "better_matched_candidate"
  | "failed_assessment"
  | "compensation_mismatch"
  | "role_closed"
  | "other";

export interface ApplicationCreateRequest {
  candidate_id: string;
  requisition_id: string;
}

export interface ApplicationResponse {
  id: string;
  candidate_id: string;
  requisition_id: string;
  assigned_to_user_id: string | null;
  status: ApplicationStatus;
  applied_at: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface ApplicationActivityItem {
  id: string;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus;
  rejection_reason: ApplicationRejectionReason | null;
  actor_display_name: string;
  transitioned_at: string;
}

export interface ApplicationActivityResponse {
  items: ApplicationActivityItem[];
}

export interface ApplicationListResponse {
  items: ApplicationResponse[];
  next_cursor?: string | null;
}

export interface ApplicationPipelineItem {
  id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  requisition_id: string;
  requisition_title: string;
  assigned_to_user_id: string | null;
  assigned_to_display_name: string | null;
  follow_up_action: string | null;
  follow_up_due_at: string | null;
  status: ApplicationStatus;
  applied_at: string;
  version: number;
  screening_progress: ApplicationScreeningProgress;
}

export type ApplicationScreeningProgress = "not_started" | "in_progress" | "complete";

export interface ApplicationAssignmentRequest {
  assigned_to_user_id: string | null;
  expected_version: number;
}

export interface ApplicationPipelineListResponse {
  items: ApplicationPipelineItem[];
  next_cursor?: string | null;
  stage_counts: Record<ApplicationStatus, number>;
}

export interface ApplicationPipelineJobSummary {
  requisition_id: string;
  requisition_title: string;
  total_count: number;
  stage_counts: Record<ApplicationStatus, number>;
  follow_up_count: number;
  overdue_follow_up_count: number;
}

export interface ApplicationPipelineSummaryResponse {
  total_count: number;
  stage_counts: Record<ApplicationStatus, number>;
  jobs: ApplicationPipelineJobSummary[];
}

export interface ApplicationFollowUp {
  id: string;
  action: string;
  due_at: string;
  created_at: string;
  completed_at: string | null;
  version: number;
}

export interface ApplicationFollowUpListResponse {
  items: ApplicationFollowUp[];
  active_follow_up_id: string | null;
}

export type ScreeningRecommendation = "advance" | "hold" | "reject";

export interface ScreeningRubricCriterion {
  id: string;
  criterion: string;
  guidance: string | null;
}

export interface ScreeningRubricResponse {
  items: ScreeningRubricCriterion[];
  version: number;
}

export interface ReplaceScreeningRubricRequest {
  expected_version: number;
  items: ScreeningRubricCriterion[];
}

export interface ScreeningCriterion {
  criterion_id?: string | null;
  criterion: string;
  guidance?: string | null;
  rating: number;
  evidence: string | null;
}

export interface ScreeningCriterionInput {
  criterion_id: string;
  rating: number;
  evidence: string | null;
}

export interface ApplicationScreeningAssessmentRequest {
  overall_rating: number;
  recommendation: ScreeningRecommendation;
  rubric_version: number;
  criteria: ScreeningCriterionInput[];
  summary: string;
}

export interface ApplicationScreeningAssessment extends Omit<ApplicationScreeningAssessmentRequest, "criteria"> {
  criteria: ScreeningCriterion[];
  id: string;
  application_id: string;
  reviewer_display_name: string;
  submitted_at: string;
}

export interface ApplicationScreeningAssessmentListResponse {
  items: ApplicationScreeningAssessment[];
  my_assessment_id: string | null;
  rubric: ScreeningRubricCriterion[];
  rubric_version: number | null;
}

export interface ScreeningCriterionComparison {
  criterion_id: string;
  criterion: string;
  average_rating: number | null;
  assessment_count: number;
}

export interface ScreeningCandidateComparison {
  application_id: string;
  candidate_name: string;
  applied_at: string;
  current_rubric_review_count: number;
  previous_rubric_review_count: number;
  average_overall_rating: number | null;
  advance_count: number;
  hold_count: number;
  reject_count: number;
  criteria: ScreeningCriterionComparison[];
}

export interface ScreeningComparisonPageResponse {
  rubric_version: number;
  rubric: ScreeningRubricCriterion[];
  items: ScreeningCandidateComparison[];
  next_cursor: string | null;
}

export interface ApplicationFollowUpRequest {
  action: string;
  due_at: string;
}

export interface ApplicationFollowUpUpdateRequest extends ApplicationFollowUpRequest {
  expected_version: number;
}

export interface ApplicationFollowUpCompleteRequest {
  expected_version: number;
}

export type HiringDecision = "advance_to_offer" | "reject";

export interface HiringDecisionResponse {
  id: string;
  application_id: string;
  decision: HiringDecision;
  rationale: string;
  rejection_reason: ApplicationRejectionReason | null;
  decided_at: string;
  created_at: string;
  version: number;
}

export interface HiringDecisionStateResponse {
  decision: HiringDecisionResponse | null;
}

export interface RecordHiringDecisionRequest {
  decision: HiringDecision;
  expected_application_version: number;
  rationale: string;
  rejection_reason?: ApplicationRejectionReason | null;
}
