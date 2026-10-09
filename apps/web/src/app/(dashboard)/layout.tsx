import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { DashboardShell } from "@/components/layout/dashboard-shell";

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const session = await auth();

  if (
    !session ||
    session.authError === "RefreshAccessTokenError" ||
    !session.supabaseAccessToken
  ) {
    redirect("/login");
  }

  return (
    <DashboardShell initialRoles={session.roles ?? []}>
      {children}
    </DashboardShell>
  );
}
