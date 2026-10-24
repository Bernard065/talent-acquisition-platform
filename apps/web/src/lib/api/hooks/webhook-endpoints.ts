"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createWebhookEndpoint,
  deleteWebhookEndpoint,
  disableWebhookEndpoint,
  listWebhookEndpoints,
  rotateWebhookEndpointSecret,
  updateWebhookEndpoint,
} from "../services/webhook-endpoints";
import type {
  CreateWebhookEndpointRequest,
  ExpectedWebhookEndpointVersionRequest,
  UpdateWebhookEndpointRequest,
} from "@/types/api/webhook-endpoints";

export const webhookEndpointQueryKeys = {
  all: ["webhook-endpoints"] as const,
  list: () => [...webhookEndpointQueryKeys.all, "list"] as const,
};

export function useWebhookEndpoints() {
  const { status } = useSession();

  return useQuery({
    queryKey: webhookEndpointQueryKeys.list(),
    queryFn: ({ signal }) => listWebhookEndpoints({ signal }),
    enabled: status === "authenticated",
  });
}

function useWebhookEndpointMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<unknown>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: webhookEndpointQueryKeys.list(),
      });
    },
  });
}

export function useCreateWebhookEndpoint() {
  return useWebhookEndpointMutation(
    ({ request, idempotencyKey }: {
      request: CreateWebhookEndpointRequest;
      idempotencyKey: string;
    }) => createWebhookEndpoint(request, { idempotencyKey }),
  );
}

export function useUpdateWebhookEndpoint() {
  return useWebhookEndpointMutation(
    ({ endpointId, request, idempotencyKey }: {
      endpointId: string;
      request: UpdateWebhookEndpointRequest;
      idempotencyKey: string;
    }) => updateWebhookEndpoint(endpointId, request, { idempotencyKey }),
  );
}

export function useRotateWebhookEndpointSecret() {
  return useWebhookEndpointMutation(
    ({ endpointId, request, idempotencyKey }: {
      endpointId: string;
      request: ExpectedWebhookEndpointVersionRequest;
      idempotencyKey: string;
    }) => rotateWebhookEndpointSecret(endpointId, request, { idempotencyKey }),
  );
}

export function useDisableWebhookEndpoint() {
  return useWebhookEndpointMutation(
    ({ endpointId, request, idempotencyKey }: {
      endpointId: string;
      request: ExpectedWebhookEndpointVersionRequest;
      idempotencyKey: string;
    }) => disableWebhookEndpoint(endpointId, request, { idempotencyKey }),
  );
}

export function useDeleteWebhookEndpoint() {
  return useWebhookEndpointMutation(
    ({ endpointId, request, idempotencyKey }: {
      endpointId: string;
      request: ExpectedWebhookEndpointVersionRequest;
      idempotencyKey: string;
    }) => deleteWebhookEndpoint(endpointId, request, { idempotencyKey }),
  );
}

\n