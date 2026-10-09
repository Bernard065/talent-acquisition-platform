"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import type { Role } from "@/types/api/auth";
import { useCurrentIdentity } from "@/lib/api/hooks/auth";
import { getAuthorizationContext } from "@/lib/auth/authorization-context";
import { identityQueryKey } from "@/lib/api/hooks/auth";
import { canAccessDashboardRoute } from "@/components/layout/dashboard-role-access";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";

export function DashboardShell({
  children,
  initialRoles,
}: {
  children: ReactNode;
  initialRoles: Role[];
}) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const identityQuery = useCurrentIdentity();
  const sessionUserId = session?.user?.id ?? null;
  const identity = identityQuery.data;
  const identityMatchesSession = identity?.subject === sessionUserId;
  const roles = identityMatchesSession ? identity.roles : initialRoles;
  const canAccessPage = canAccessDashboardRoute(pathname, roles);
  const authorizationContext = identityMatchesSession
    ? getAuthorizationContext(identity.subject, identity.roles, identity.tenant_id)
    : null;
  const previousUserId = useRef<string | null>(sessionUserId);
  const previousAuthorizationContext = useRef<string | null>(null);

  useEffect(() => {
    if (previousUserId.current !== sessionUserId) {
      previousUserId.current = sessionUserId;
      previousAuthorizationContext.current = null;
    }
  }, [sessionUserId]);

  useEffect(() => {
    if (!identityMatchesSession || !identity || !authorizationContext) return;

    if (
      previousAuthorizationContext.current !== null &&
      previousAuthorizationContext.current !== authorizationContext
    ) {
      queryClient.removeQueries({
        predicate: (query) =>
          query.queryKey.length !== identityQueryKey.length ||
          query.queryKey.some((part, index) => part !== identityQueryKey[index]),
      });
    }

    previousAuthorizationContext.current = authorizationContext;
  }, [authorizationContext, identity, identityMatchesSession, queryClient]);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 ease-in-out md:relative md:translate-x-0 ${isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <Sidebar
          roles={roles}
          onClose={() => setIsMobileMenuOpen(false)}
        />
      </div>

      <div className="flex w-full min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar
          roles={roles}
          onMenuClick={() => setIsMobileMenuOpen(true)}
        />
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 md:p-6 lg:p-8">
          {canAccessPage ? (
            children
          ) : (
            <section
              aria-labelledby="dashboard-access-denied-title"
              className="mx-auto mt-10 max-w-xl rounded-xl border border-amber-200 bg-amber-50 p-6"
            >
              <h1
                id="dashboard-access-denied-title"
                className="font-semibold text-amber-950"
              >
                This page isn’t available for your workspace role
              </h1>
              <p className="mt-2 text-sm text-amber-900">
                Contact your workspace admin if you need access.
              </p>
              <Link
                href="/dashboard"
                className="mt-4 inline-block text-sm font-semibold text-sr-green hover:underline"
              >
                Return to dashboard
              </Link>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
