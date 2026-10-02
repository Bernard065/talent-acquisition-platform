export type Role =
  | "tenant_admin"
  | "recruiter"
  | "hiring_manager"
  | "interviewer"
  | "people_operations"
  | "analyst";

export interface CurrentIdentityResponse {
  tenant_id: string;
  subject: string;
  roles: Role[];
}
