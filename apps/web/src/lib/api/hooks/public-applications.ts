"use client";

import { useMutation } from "@tanstack/react-query";
import {
  scanPublicJobApplicationResume,
  submitPublicJobApplication,
} from "@/lib/api/services/public-applications";

export function useScanPublicJobApplicationResume() {
  return useMutation({
    mutationFn: ({ publicJobId, request, idempotencyKey }: {
      publicJobId: string;
      request: FormData;
      idempotencyKey: string;
    }) => scanPublicJobApplicationResume(publicJobId, request, idempotencyKey),
    retry: 0,
  });
}

export function useSubmitPublicJobApplication() {
  return useMutation({
    mutationFn: ({
      publicJobId,
      request,
      idempotencyKey,
    }: {
      publicJobId: string;
      request: FormData;
      idempotencyKey: string;
    }) =>
      submitPublicJobApplication(publicJobId, request, idempotencyKey),
    retry: 0,
  });
}
