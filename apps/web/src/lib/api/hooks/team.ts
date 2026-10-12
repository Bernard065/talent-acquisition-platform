"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createTeamInvitation,
  grantTeamMemberInterviewerRole,
  listTeamInvitations,
  listTeamInterviewers,
  listTeamMembers,
  listWorkspaceMembers,
  revokeTeamInvitation,
} from "../services/team";
import type { CreateTeamInvitationRequest } from "@/types/api/team";

export const teamQueryKeys = {
  all: ["team"] as const,
  invitations: () => [...teamQueryKeys.all, "invitations"] as const,
  members: () => [...teamQueryKeys.all, "members"] as const,
  workspaceMembers: () => [...teamQueryKeys.all, "workspace-members"] as const,
  interviewers: () => [...teamQueryKeys.all, "interviewers"] as const,
};

export function useTeamMembers() {
  const { status } = useSession();

  return useQuery({
    queryKey: teamQueryKeys.members(),
    queryFn: ({ signal }) => listTeamMembers({ signal }),
    enabled: status === "authenticated",
  });
}

export function useWorkspaceMembers() {
  const { status } = useSession();

  return useQuery({
    queryKey: teamQueryKeys.workspaceMembers(),
    queryFn: ({ signal }) => listWorkspaceMembers({ signal }),
    enabled: status === "authenticated",
  });
}

export function useTeamInterviewers() {
  const { status } = useSession();

  return useQuery({
    queryKey: teamQueryKeys.interviewers(),
    queryFn: ({ signal }) => listTeamInterviewers({ signal }),
    enabled: status === "authenticated",
  });
}

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

export function useGrantTeamMemberInterviewerRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (memberId: string) => grantTeamMemberInterviewerRole(memberId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: teamQueryKeys.interviewers() }),
        queryClient.invalidateQueries({ queryKey: teamQueryKeys.members() }),
      ]);
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
