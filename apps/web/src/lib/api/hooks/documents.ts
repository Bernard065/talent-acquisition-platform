"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  getCandidateDocumentDownloadAuthorization,
  getCandidateDocumentPreviewAuthorization,
  listCandidateDocuments,
} from "../services/documents";

export const candidateDocumentQueryKeys = {
  all: ["candidate-documents"] as const,
  byCandidate: (candidateId: string) =>
    [...candidateDocumentQueryKeys.all, "candidate", candidateId] as const,
};

export function useCandidateDocuments(candidateId: string) {
  const { status } = useSession();

  return useQuery({
    queryKey: candidateDocumentQueryKeys.byCandidate(candidateId),
    queryFn: ({ signal }) => listCandidateDocuments(candidateId, signal),
    enabled: status === "authenticated" && Boolean(candidateId),
    refetchInterval: (query) =>
      query.state.data?.some((document) =>
        document.status === "pending_upload" ||
        document.status === "uploaded" ||
        document.status === "scanning",
      )
        ? 2_000
        : false,
  });
}

export function useCandidateDocumentDownload() {
  return useMutation({
    mutationFn: (documentId: string) =>
      getCandidateDocumentDownloadAuthorization(documentId),
  });
}

export function useCandidateDocumentPreview() {
  return useMutation({
    mutationFn: (documentId: string) =>
      getCandidateDocumentPreviewAuthorization(documentId),
  });
}
