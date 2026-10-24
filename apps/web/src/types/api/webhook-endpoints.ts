export type WebhookEndpointStatus = "active" | "disabled";

export interface WebhookEndpoint {
  id: string;
  name: string;
  url: string;
  status: WebhookEndpointStatus;
  event_types: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WebhookEndpointListResponse {
  items: WebhookEndpoint[];
}

export interface CreateWebhookEndpointRequest {
  name: string;
  url: string;
  event_types: string[];
}

export interface UpdateWebhookEndpointRequest extends CreateWebhookEndpointRequest {
  expected_version: number;
}

export interface ExpectedWebhookEndpointVersionRequest {
  expected_version: number;
}

export interface WebhookEndpointDeletedResponse {
  id: string;
  status: "deleted";
}

\n