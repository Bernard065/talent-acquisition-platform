"use client";

import { SessionProvider, signOut, useSession } from "next-auth/react";
import { useEffect, type ReactNode } from "react";
import { setTokenAccessor } from "@/lib/api";

function ApiTokenBridge() {
  const { data: session } = useSession();

  useEffect(() => {
    setTokenAccessor(() => session?.supabaseAccessToken ?? null);
    if (session?.authError) void signOut({ redirectTo: "/login" });
  }, [session?.authError, session?.supabaseAccessToken]);

  return null;
}

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <ApiTokenBridge />
      {children}
    </SessionProvider>
  );
}
