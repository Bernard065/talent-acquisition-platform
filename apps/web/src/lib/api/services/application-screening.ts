import { get, post, type RequestOptions } from "../client";
import type {
  ApplicationScreeningAssessmentListResponse,
  ApplicationScreeningAssessmentRequest,
  ApplicationScreeningAssessment,
} from "@/types/api";

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
