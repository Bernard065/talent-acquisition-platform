import { post, type RequestOptions } from "../client";
import type {
  PublicApplicationAcceptedResponse,
  SubmitPublicApplicationRequest,
} from "@/types/api/public-applications";

export function submitPublicJobApplication(
  publicJobId: string,
  body: SubmitPublicApplicationRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<PublicApplicationAcceptedResponse> {
  return post<PublicApplicationAcceptedResponse>(
    `/public/jobs/${publicJobId}/applications`,
    body,
    { ...options, idempotencyKey },
  );
}
