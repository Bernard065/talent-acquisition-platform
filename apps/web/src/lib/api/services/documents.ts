import { get } from "../client";
import type {
  CandidateDocumentDownloadAuthorizationResponse,
  CandidateDocumentResponse,
} from "@/types/api";

export function listCandidateDocuments(
  candidateId: string,
  signal?: AbortSignal,
): Promise<CandidateDocumentResponse[]> {
  return get<CandidateDocumentResponse[]>("/candidate-documents", {
    params: { candidate_id: candidateId },
    signal,
  });
}

export function getCandidateDocumentDownloadAuthorization(
  documentId: string,
  signal?: AbortSignal,
): Promise<CandidateDocumentDownloadAuthorizationResponse> {
  return get<CandidateDocumentDownloadAuthorizationResponse>(
    `/candidate-documents/${documentId}/download-authorizations`,
    { signal },
  );
}

export function getCandidateDocumentPreviewAuthorization(
  documentId: string,
  signal?: AbortSignal,
): Promise<CandidateDocumentDownloadAuthorizationResponse> {
  return get<CandidateDocumentDownloadAuthorizationResponse>(
    `/candidate-documents/${documentId}/preview-authorizations`,
    { signal },
  );
}
