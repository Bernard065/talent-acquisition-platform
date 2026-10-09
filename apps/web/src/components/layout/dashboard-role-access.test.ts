import { describe, expect, it } from "vitest";
import { canAccessDashboardRoute } from "@/components/layout/dashboard-role-access";

describe("dashboard page role access", () => {
  it("limits recruiting pages to roles authorized by the API", () => {
    expect(canAccessDashboardRoute("/dashboard/candidates", ["recruiter"])).toBe(true);
    expect(canAccessDashboardRoute("/dashboard/candidates/123", ["analyst"])).toBe(false);
    expect(canAccessDashboardRoute("/dashboard/jobs/123", ["analyst"])).toBe(true);
  });

  it("applies write roles to requisition creation and admin access to team", () => {
    expect(canAccessDashboardRoute("/dashboard/jobs/new", ["recruiter"])).toBe(true);
    expect(canAccessDashboardRoute("/dashboard/jobs/new", ["analyst"])).toBe(false);
    expect(canAccessDashboardRoute("/dashboard/team", ["tenant_admin"])).toBe(true);
    expect(canAccessDashboardRoute("/dashboard/team", ["recruiter"])).toBe(false);
  });

  it("allows interviewers to view interview pages and denies unrelated routes", () => {
    expect(canAccessDashboardRoute("/dashboard/interviews", ["interviewer"])).toBe(true);
    expect(canAccessDashboardRoute("/dashboard/analytics", ["interviewer"])).toBe(false);
    expect(canAccessDashboardRoute("/dashboard", ["interviewer"])).toBe(true);
  });

  it("denies unlisted dashboard routes", () => {
    expect(
      canAccessDashboardRoute(
        "/dashboard/unregistered-sensitive-page",
        ["analyst"],
      ),
    ).toBe(false);
    expect(
      canAccessDashboardRoute("/dashboard/jobs/123/edit", ["analyst"]),
    ).toBe(false);
  });

  it("aligns recruiter Approval settings route access with its sidebar policy", () => {
    expect(
      canAccessDashboardRoute("/dashboard/settings/approvals", ["recruiter"]),
    ).toBe(true);
    expect(
      canAccessDashboardRoute("/dashboard/settings", ["interviewer"]),
    ).toBe(true);
  });
});
