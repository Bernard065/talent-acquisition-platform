"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { useCurrentIdentity } from "@/lib/api/hooks/auth";
import { MindHireMark, LayoutDashboard, BriefcaseBusiness, FileText, Users, List, CalendarDays, ChartNoAxesColumnIncreasing, UsersRound, Settings, X } from "@/components/icons";

const navigation = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    name: "Jobs",
    href: "/dashboard/jobs",
    icon: BriefcaseBusiness,
  },
  {
    name: "Requisitions",
    href: "/dashboard/requisitions",
    icon: FileText,
  },
  {
    name: "Approvals",
    href: "/dashboard/approvals",
    icon: FileText,
  },
  {
    name: "Candidates",
    href: "/dashboard/candidates",
    icon: Users,
  },
  {
    name: "Applications",
    href: "/dashboard/applications",
    icon: List,
  },
  {
    name: "Interviews",
    href: "/dashboard/interviews",
    icon: CalendarDays,
  },
  {
    name: "Analytics",
    href: "/dashboard/analytics",
    icon: ChartNoAxesColumnIncreasing,
  },
  {
    name: "Team",
    href: "/dashboard/team",
    icon: UsersRound,
  },
  {
    name: "Settings",
    href: "/dashboard/settings",
    icon: Settings,
  },
];

const adminNavigation = [
  {
    name: "Approval settings",
    href: "/dashboard/settings/approvals",
    icon: Settings,
  },
];

export const Sidebar = ({ onClose }: { onClose?: () => void }) => {
  const pathname = usePathname();
  const { data: session } = useSession();
  const identityQuery = useCurrentIdentity();
  const isWorkspaceAdmin = identityQuery.data?.roles.includes("tenant_admin") ?? false;
  const userLabel = session?.user?.name || session?.user?.email || "Workspace member";
  const initials = userLabel
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase())
    .join("");

  return (
    <aside className="w-64 border-r border-gray-200 bg-white flex flex-col h-full h-[100dvh]">
      {/* Brand */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 shrink-0">
        <Link href="/" className="flex items-center gap-2 group">
          <MindHireMark className="h-7 w-7 text-sr-green transition-colors" />
          <span className="font-display font-bold text-xl tracking-tight text-sr-text-blue">MindHire</span>
        </Link>
        {onClose && (
          <button onClick={onClose} className="md:hidden text-gray-500 hover:text-sr-text-blue p-1">
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto py-6 px-4">
        <nav className="flex flex-col gap-1">
          {[...navigation, ...(isWorkspaceAdmin ? adminNavigation : [])].map((item) => {
            const isActive = pathname === item.href || (
              item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`)
            );
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-gray-100 text-sr-text-blue"
                    : "text-gray-600 hover:text-sr-text-blue hover:bg-gray-50"
                }`}
              >
                <div className={`${isActive ? "text-sr-green" : "text-gray-400"}`}>
                  <item.icon className="w-5 h-5" aria-hidden="true" />
                </div>
                {item.name}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* User Mini Profile */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="w-9 h-9 rounded-full bg-sr-mint text-sr-text-blue flex items-center justify-center font-bold text-sm">
            {initials || "WM"}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-semibold text-sr-text-blue">{userLabel}</span>
            {session?.user?.email && session.user.email !== userLabel && (
              <span className="truncate text-xs text-gray-500">{session.user.email}</span>
            )}
          </div>
          <button
            type="button"
            onClick={() => void signOut({ redirectTo: "/login" })}
            className="text-xs font-medium text-gray-500 hover:text-sr-text-blue"
          >
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
};
