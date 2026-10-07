"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createTeamInvitation,
  listTeamInvitations,
  revokeTeamInvitation,
} from "../services/team";
import type { CreateTeamInvitationRequest } from "@/types/api/team";

export const teamQueryKeys = {
  all: ["team"] as const,
  invitations: () => [...teamQueryKeys.all, "invitations"] as const,
};

export function useTeamInvitations() {
  const { status } = useSession();

  return useQuery({
    queryKey: teamQueryKeys.invitations(),
    queryFn: ({ signal }) => listTeamInvitations({ signal }),
    enabled: status === "authenticated",
  });
}

export function useCreateTeamInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ request }: {
      request: CreateTeamInvitationRequest;
    }) => createTeamInvitation(request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: teamQueryKeys.invitations() });
    },
  });
}

export function useRevokeTeamInvitation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invitationId: string) => revokeTeamInvitation(invitationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: teamQueryKeys.invitations() });
    },
  });
}
