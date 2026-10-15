"use client";
import { InlineSvgIcon004 as MenuIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { getUserDisplayName } from "@/lib/user-display-name";
import type { Role } from "@/types/api/auth";
import { dashboardRolePolicies } from "@/components/layout/dashboard-role-access";
import { NotificationCenter } from "@/components/layout/notification-center";

const pageTitles: Array<{ href: string; title: string }> = [
  { href: "/dashboard/jobs/new", title: "Create requisition" },
  { href: "/dashboard/requisitions", title: "Requisitions" },
  { href: "/dashboard/settings/approvals", title: "Approval settings" },
  { href: "/dashboard/settings/calendar-sync", title: "Calendar sync" },
  { href: "/dashboard/approvals", title: "Approvals" },
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
  isMenuOpen = false,
  menuControlsId,
}: {
  roles: Role[];
  onMenuClick?: () => void;
  isMenuOpen?: boolean;
  menuControlsId?: string;
}) => {
  const pathname = usePathname() ?? "";
  const { data: session } = useSession();
  const pageTitle = [...pageTitles]
    .sort((left, right) => right.href.length - left.href.length)
    .find(({ href }) => pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`)))
    ?.title ?? "Dashboard";
  const canCreateRequisition = dashboardRolePolicies.requisitionCreate.some((role) =>
    roles.includes(role),
  );
  const name = getUserDisplayName(session?.user?.name, session?.user?.email) || "Workspace member";
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => Array.from(part)[0]?.toLocaleUpperCase())
    .join("");
  const isCreatingRequisition = pathname === "/dashboard/jobs/new" || pathname.startsWith("/dashboard/jobs/new/");

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-4 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 items-center md:hidden">
          <Button
            variant="ghost"
            size="icon"
            aria-label={isMenuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={isMenuOpen}
            aria-controls={menuControlsId}
            className="text-gray-500 hover:text-sr-text-blue"
            onClick={onMenuClick}
          >
            <MenuIcon className="h-6 w-6" aria-hidden="true" />
          </Button>
        </div>
        <p className="truncate text-base font-semibold text-sr-text-blue">{pageTitle}</p>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {canCreateRequisition && !isCreatingRequisition && (
          <Button variant="outline" className="hidden h-9 border-gray-200 text-sm font-medium text-sr-text-blue hover:bg-gray-50 hover:text-sr-text-blue lg:inline-flex" asChild>
            <Link href="/dashboard/jobs/new">Create requisition</Link>
          </Button>
        )}
        <NotificationCenter />
        <div className="sr-only text-right md:not-sr-only md:block">
          <span className="block max-w-48 truncate text-sm font-medium text-sr-text-blue">{name}</span>
        </div>
        <div aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-sr-mint text-xs font-bold text-sr-text-blue">
          {initials || "WM"}
        </div>
      </div>
    </header>
  );
};
