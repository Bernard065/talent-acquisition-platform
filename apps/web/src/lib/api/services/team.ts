import { del, get, post, type RequestOptions } from "../client";
import type {
  CreateTeamInvitationRequest,
  TeamInvitation,
} from "@/types/api/team";

export async function listTeamInvitations(
  options?: RequestOptions,
): Promise<TeamInvitation[]> {
  return get<TeamInvitation[]>("/team/invitations", options);
}

export async function createTeamInvitation(
  request: CreateTeamInvitationRequest,
  options?: RequestOptions,
): Promise<TeamInvitation> {
  return post<TeamInvitation>("/team/invitations", request, options);
}

export async function revokeTeamInvitation(
  invitationId: string,
  options?: RequestOptions,
): Promise<void> {
  return del<void>(`/team/invitations/${invitationId}`, options);
}
