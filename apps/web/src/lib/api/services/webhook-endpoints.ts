import { apiRequest, get, post, put, type RequestOptions } from "../client";
import type {
  CreateWebhookEndpointRequest,
  ExpectedWebhookEndpointVersionRequest,
  WebhookEndpoint,
  WebhookEndpointDeletedResponse,
  WebhookEndpointListResponse,
  UpdateWebhookEndpointRequest,
} from "@/types/api/webhook-endpoints";

export function listWebhookEndpoints(
  options?: RequestOptions,
): Promise<WebhookEndpointListResponse> {
  return get<WebhookEndpointListResponse>("/webhook-endpoints", options);
}

export function createWebhookEndpoint(
  request: CreateWebhookEndpointRequest,
  options?: RequestOptions,
): Promise<WebhookEndpoint> {
  return post<WebhookEndpoint>("/webhook-endpoints", request, options);
}

export function updateWebhookEndpoint(
  endpointId: string,
  request: UpdateWebhookEndpointRequest,
  options?: RequestOptions,
): Promise<WebhookEndpoint> {
  return put<WebhookEndpoint>(`/webhook-endpoints/${endpointId}`, request, options);
}

export function rotateWebhookEndpointSecret(
  endpointId: string,
  request: ExpectedWebhookEndpointVersionRequest,
  options?: RequestOptions,
): Promise<WebhookEndpoint> {
  return post<WebhookEndpoint>(
    `/webhook-endpoints/${endpointId}/secret-rotations`,
    request,
    options,
  );
}

export function disableWebhookEndpoint(
  endpointId: string,
  request: ExpectedWebhookEndpointVersionRequest,
  options?: RequestOptions,
): Promise<WebhookEndpoint> {
  return post<WebhookEndpoint>(
    `/webhook-endpoints/${endpointId}/disable`,
    request,
    options,
  );
}

export function deleteWebhookEndpoint(
  endpointId: string,
  request: ExpectedWebhookEndpointVersionRequest,
  options?: RequestOptions,
): Promise<WebhookEndpointDeletedResponse> {
  return apiRequest<WebhookEndpointDeletedResponse>(
    "DELETE",
    `/webhook-endpoints/${endpointId}`,
    request,
    options,
  );
}

\n