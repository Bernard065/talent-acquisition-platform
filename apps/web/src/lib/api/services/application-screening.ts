import { get, post, type RequestOptions } from "../client";
import type {
  ApplicationScreeningAssessmentListResponse,
  ApplicationScreeningAssessmentRequest,
  ApplicationScreeningAssessment,
  ScreeningComparisonPageResponse,
} from "@/types/api";

export interface ScreeningComparisonParams {
  limit?: number;
  cursor?: string;
}

export async function getJobScreeningComparison(
  jobPostingId: string,
  params?: ScreeningComparisonParams,
  options?: RequestOptions,
): Promise<ScreeningComparisonPageResponse> {
  return get<ScreeningComparisonPageResponse>(
    `/job-postings/${jobPostingId}/screening-comparison`,
    { ...options, params: { ...options?.params, ...params } },
  );
}

export async function listApplicationScreeningAssessments(
  applicationId: string,
  options?: RequestOptions,
): Promise<ApplicationScreeningAssessmentListResponse> {
  return get<ApplicationScreeningAssessmentListResponse>(
    `/applications/${applicationId}/screening-assessments`,
    options,
  );
}

export async function submitApplicationScreeningAssessment(
  applicationId: string,
  assessment: ApplicationScreeningAssessmentRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<ApplicationScreeningAssessment> {
  return post<ApplicationScreeningAssessment>(
    `/applications/${applicationId}/screening-assessments`,
    assessment,
    { ...options, idempotencyKey },
  );
}
