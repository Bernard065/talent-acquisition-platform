export type TeamRole =
  | "tenant_admin"
  | "recruiter"
  | "hiring_manager"
  | "interviewer"
  | "people_operations"
  | "analyst";

export type TeamInvitationStatus = "pending" | "accepted" | "revoked" | "expired";

export interface TeamInvitation {
  id: string;
  email: string;
  role: TeamRole;
  status: TeamInvitationStatus;
  created_at: string;
  expires_at: string;
}

export interface CreateTeamInvitationRequest {
  email: string;
  role: Exclude<TeamRole, "tenant_admin">;
}
