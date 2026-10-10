"use client";

import { useMutation } from "@tanstack/react-query";
import { submitPublicJobApplication } from "@/lib/api/services/public-applications";
import type { SubmitPublicApplicationRequest } from "@/types/api/public-applications";

export function useSubmitPublicJobApplication() {
  return useMutation({
    mutationFn: ({
      publicJobId,
      request,
      idempotencyKey,
    }: {
      publicJobId: string;
      request: SubmitPublicApplicationRequest;
      idempotencyKey: string;
    }) =>
      submitPublicJobApplication(publicJobId, request, idempotencyKey),
    retry: 0,
  });
}
