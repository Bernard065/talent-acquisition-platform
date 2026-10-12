import { del, get, post, put, type RequestOptions } from "../client";
import type {
  CreateTeamInvitationRequest,
  TeamMemberListResponse,
  TeamInvitation,
  InterviewerListResponse,
} from "@/types/api/team";

export async function listTeamMembers(
  options?: RequestOptions,
): Promise<TeamMemberListResponse> {
  return get<TeamMemberListResponse>("/team/members", options);
}

export async function listWorkspaceMembers(
  options?: RequestOptions,
): Promise<TeamMemberListResponse> {
  return get<TeamMemberListResponse>("/team/workspace-members", options);
}

export async function listTeamInterviewers(
  options?: RequestOptions,
): Promise<InterviewerListResponse> {
  return get<InterviewerListResponse>("/team/interviewers", options);
}

export async function grantTeamMemberInterviewerRole(
  memberId: string,
  options?: RequestOptions,
): Promise<void> {
  return put<void>(`/team/members/${memberId}/roles/interviewer`, undefined, options);
}

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
