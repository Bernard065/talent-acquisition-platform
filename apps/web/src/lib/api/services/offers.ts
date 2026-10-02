import { get, post, type RequestOptions } from "../client";
import type {
  OfferResponse,
  CreateOfferRequest,
  ExpectedOfferVersionRequest,
} from "@/types/api";

export async function getOffer(
  id: string,
  options?: RequestOptions,
): Promise<OfferResponse> {
  return get<OfferResponse>(`/offers/${id}`, options);
}

export async function createOffer(
  body: CreateOfferRequest,
  idempotencyKey: string,
  options?: RequestOptions,
): Promise<OfferResponse> {
  return post<OfferResponse>("/offers", body, {
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
