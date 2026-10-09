import type { Role } from "@/types/api/auth";

export const dashboardRolePolicies = {
  allWorkspaceMembers: [
    "tenant_admin",
    "recruiter",
    "hiring_manager",
    "interviewer",
    "people_operations",
    "analyst",
  ],
  recruiting: ["tenant_admin", "recruiter", "people_operations"],
  jobAndRequisitionRead: [
    "tenant_admin",
    "recruiter",
    "hiring_manager",
    "analyst",
  ],
  requisitionCreate: ["tenant_admin", "recruiter"],
  approvalSettings: ["tenant_admin", "recruiter"],
  analytics: ["tenant_admin", "recruiter", "people_operations", "analyst"],
  interviewCalendar: ["tenant_admin", "recruiter", "people_operations", "interviewer"],
  workspaceAdmin: ["tenant_admin"],
} as const satisfies Record<string, readonly Role[]>;

type DashboardRouteRule = {
  path: string;
  match: "exact" | "detail";
  roles: readonly Role[];
};

const dashboardRouteRules: readonly DashboardRouteRule[] = [
  { path: "/dashboard/jobs/new", match: "exact", roles: dashboardRolePolicies.requisitionCreate },
  { path: "/dashboard/requisitions/new", match: "exact", roles: dashboardRolePolicies.requisitionCreate },
  { path: "/dashboard/settings/approvals", match: "exact", roles: dashboardRolePolicies.approvalSettings },
  { path: "/dashboard/team", match: "exact", roles: dashboardRolePolicies.workspaceAdmin },
  { path: "/dashboard/candidates", match: "exact", roles: dashboardRolePolicies.recruiting },
  { path: "/dashboard/candidates", match: "detail", roles: dashboardRolePolicies.recruiting },
  { path: "/dashboard/applications", match: "exact", roles: dashboardRolePolicies.recruiting },
  { path: "/dashboard/applications", match: "detail", roles: dashboardRolePolicies.recruiting },
  { path: "/dashboard/interviews", match: "exact", roles: dashboardRolePolicies.interviewCalendar },
  { path: "/dashboard/interviews", match: "detail", roles: dashboardRolePolicies.interviewCalendar },
  { path: "/dashboard/analytics", match: "exact", roles: dashboardRolePolicies.analytics },
  { path: "/dashboard/jobs", match: "exact", roles: dashboardRolePolicies.jobAndRequisitionRead },
  { path: "/dashboard/jobs", match: "detail", roles: dashboardRolePolicies.jobAndRequisitionRead },
  { path: "/dashboard/requisitions", match: "exact", roles: dashboardRolePolicies.jobAndRequisitionRead },
  { path: "/dashboard/approvals", match: "exact", roles: dashboardRolePolicies.allWorkspaceMembers },
  { path: "/dashboard/approvals", match: "detail", roles: dashboardRolePolicies.allWorkspaceMembers },
  { path: "/dashboard/settings", match: "exact", roles: dashboardRolePolicies.allWorkspaceMembers },
];

export function canAccessDashboardRoute(pathname: string, roles: Role[]): boolean {
  const normalizedPathname = pathname.replace(/\/+$/, "") || "/";
  if (normalizedPathname === "/dashboard") {
    return dashboardRolePolicies.allWorkspaceMembers.some((role) =>
      roles.includes(role),
    );
  }

  const rule = dashboardRouteRules.find(({ path, match }) => {
    if (match === "exact") return normalizedPathname === path;
    const detailPath = normalizedPathname.slice(path.length + 1);
    return normalizedPathname.startsWith(`${path}/`) && !detailPath.includes("/");
  });

  return rule !== undefined && rule.roles.some((role) => roles.includes(role));
}
