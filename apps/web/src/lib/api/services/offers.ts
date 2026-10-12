import { get, post, type RequestOptions } from "../client";
import type {
  ApplicationOffersResponse,
  OfferResponse,
  CreateOfferRequest,
  ExpectedOfferVersionRequest,
} from "@/types/api";

export async function listApplicationOffers(
  applicationId: string,
  options?: RequestOptions,
): Promise<ApplicationOffersResponse> {
  return get<ApplicationOffersResponse>(
    `/applications/${applicationId}/offers`,
    options,
  );
}

export async function createOffer(
  applicationId: string,
  body: CreateOfferRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<OfferResponse> {
  return post<OfferResponse>(`/applications/${applicationId}/offers`, body, {
    ...options,
    idempotencyKey,
  });
}

export async function requestOfferApproval(
  id: string,
  body: ExpectedOfferVersionRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<OfferResponse> {
  return post<OfferResponse>(`/offers/${id}/approvals`, body, {
    ...options,
    idempotencyKey,
  });
}
