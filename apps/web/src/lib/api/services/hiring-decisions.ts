import { get, post, type RequestOptions } from "../client";
import type {
  HiringDecisionResponse,
  HiringDecisionStateResponse,
  RecordHiringDecisionRequest,
} from "@/types/api/applications";

export async function getApplicationHiringDecision(
  applicationId: string,
  options?: RequestOptions,
): Promise<HiringDecisionStateResponse> {
  return get<HiringDecisionStateResponse>(
    `/applications/${applicationId}/debrief-decision`,
    options,
  );
}

export async function recordApplicationHiringDecision(
  applicationId: string,
  body: RecordHiringDecisionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<HiringDecisionResponse> {
  return post<HiringDecisionResponse>(
    `/applications/${applicationId}/debrief-decision`,
    body,
    { ...options, idempotencyKey },
  );
}
