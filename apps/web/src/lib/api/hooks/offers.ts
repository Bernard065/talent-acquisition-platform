"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { applicationQueryKeys } from "./applications";
import { createOffer, listApplicationOffers } from "../services/offers";
import type { CreateOfferRequest } from "@/types/api";

export const offerQueryKeys = {
  all: ["offers"] as const,
  application: (applicationId: string) =>
    [...offerQueryKeys.all, "application", applicationId] as const,
};

export function useApplicationOffers(applicationId: string, enabled = true) {
  const { status } = useSession();

  return useQuery({
    queryKey: offerQueryKeys.application(applicationId),
    queryFn: ({ signal }) => listApplicationOffers(applicationId, { signal }),
    enabled: status === "authenticated" && enabled && Boolean(applicationId),
  });
}

export function useCreateApplicationOffer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ applicationId, offer, idempotencyKey }: {
      applicationId: string;
      offer: CreateOfferRequest;
      idempotencyKey: string;
    }) => createOffer(applicationId, offer, idempotencyKey),
    onSuccess: async (_offer, { applicationId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: offerQueryKeys.application(applicationId) }),
        queryClient.invalidateQueries({ queryKey: applicationQueryKeys.detail(applicationId) }),
      ]);
    },
  });
}
