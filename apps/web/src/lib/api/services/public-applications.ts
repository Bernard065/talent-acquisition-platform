import { post, type RequestOptions } from "../client";
import type {
  PublicApplicationAcceptedResponse,
  PublicApplicationResumeScanResponse,
} from "@/types/api/public-applications";

export function scanPublicJobApplicationResume(
  publicJobId: string,
  body: FormData,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<PublicApplicationResumeScanResponse> {
  return post<PublicApplicationResumeScanResponse>(
    `/public/jobs/${publicJobId}/resume-scans`,
    body,
    { ...options, idempotencyKey },
  );
}

export function submitPublicJobApplication(
  publicJobId: string,
  body: FormData,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<PublicApplicationAcceptedResponse> {
  return post<PublicApplicationAcceptedResponse>(
    `/public/jobs/${publicJobId}/applications`,
    body,
    { ...options, idempotencyKey },
  );
}
