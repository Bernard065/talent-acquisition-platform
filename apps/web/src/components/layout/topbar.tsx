"use client";
import { InlineSvgIcon004 } from "@/components/icons";


import { Button } from "@/components/ui/button";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { getUserDisplayName } from "@/lib/user-display-name";
import type { Role } from "@/types/api/auth";
import { dashboardRolePolicies } from "@/components/layout/dashboard-role-access";

const pageTitles: Array<{ href: string; title: string }> = [
  { href: "/dashboard/jobs/new", title: "Create requisition" },
  { href: "/dashboard/requisitions", title: "Requisitions" },
  { href: "/dashboard/jobs", title: "Jobs" },
  { href: "/dashboard/candidates", title: "Candidates" },
  { href: "/dashboard/interviews", title: "Interviews" },
  { href: "/dashboard/analytics", title: "Analytics" },
  { href: "/dashboard/settings", title: "Settings" },
  { href: "/dashboard", title: "Dashboard" },
];

export const Topbar = ({
  roles,
  onMenuClick,
}: {
  roles: Role[];
  onMenuClick?: () => void;
}) => {
  const pathname = usePathname();
  const { data: session } = useSession();
  const pageTitle = pageTitles.find(({ href }) => pathname === href || pathname.startsWith(`${href}/`))?.title ?? "Dashboard";
  const canCreateRequisition = dashboardRolePolicies.requisitionCreate.some((role) =>
    roles.includes(role),
  );
  const name = getUserDisplayName(session?.user?.name, session?.user?.email) || "Workspace member";
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toLocaleUpperCase()).join("");

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-4 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 items-center md:hidden">
          <Button variant="ghost" size="icon" aria-label="Open navigation" className="text-gray-500 hover:text-sr-text-blue" onClick={onMenuClick}>
            <InlineSvgIcon004 className="h-6 w-6" />
          </Button>
        </div>
        <h1 className="truncate text-base font-semibold text-sr-text-blue">{pageTitle}</h1>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {canCreateRequisition && pathname !== "/dashboard/jobs/new" && (
          <Button variant="outline" className="hidden h-9 border-gray-200 text-sm font-medium text-sr-text-blue hover:bg-gray-50 hover:text-sr-text-blue lg:flex" asChild>
            <Link href="/dashboard/jobs/new">Create requisition</Link>
          </Button>
        )}
        <div className="hidden text-right md:block">
          <span className="block max-w-48 truncate text-sm font-medium text-sr-text-blue">{name}</span>
        </div>
        <div aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-sr-mint text-xs font-bold text-sr-text-blue">
          {initials || "WM"}
        </div>
      </div>
    </header>
  );
};
