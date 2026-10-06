"use client";

import { Button } from "@/components/ui/button";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";

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

export const Topbar = ({ onMenuClick }: { onMenuClick?: () => void }) => {
  const pathname = usePathname();
  const { data: session } = useSession();
  const pageTitle = pageTitles.find(({ href }) => pathname === href || pathname.startsWith(`${href}/`))?.title ?? "Dashboard";
  const name = session?.user?.name || session?.user?.email || "Workspace member";
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toLocaleUpperCase()).join("");

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-4 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 items-center md:hidden">
          <Button variant="ghost" size="icon" aria-label="Open navigation" className="text-gray-500 hover:text-sr-text-blue" onClick={onMenuClick}>
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </Button>
        </div>
        <h1 className="truncate text-base font-semibold text-sr-text-blue">{pageTitle}</h1>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        {pathname !== "/dashboard/jobs/new" && (
          <Button variant="outline" className="hidden h-9 border-gray-200 text-sm font-medium text-sr-text-blue hover:bg-gray-50 hover:text-sr-text-blue lg:flex" asChild>
            <Link href="/dashboard/jobs/new">Create requisition</Link>
          </Button>
        )}
        <div className="hidden text-right md:block">
          <span className="block max-w-48 truncate text-sm font-medium text-sr-text-blue">{name}</span>
          {session?.user?.email && session.user.email !== name && (
            <span className="block max-w-48 truncate text-xs text-gray-500">{session.user.email}</span>
          )}
        </div>
        <div aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-sr-mint text-xs font-bold text-sr-text-blue">
          {initials || "WM"}
        </div>
      </div>
    </header>
  );
};
