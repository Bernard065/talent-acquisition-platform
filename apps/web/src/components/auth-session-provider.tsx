"use client";

import { SessionProvider, signOut, useSession } from "next-auth/react";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { setTokenAccessor } from "@/lib/api";
import { hasAuthenticatedIdentityChanged } from "@/lib/auth/authorization-context";

function ApiTokenBridge() {
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  const previousUserId = useRef<string | null>(null);
  const token = session?.supabaseAccessToken ?? null;
  const userId = session?.user?.id ?? null;

  useEffect(() => {
    setTokenAccessor(() => token);
  }, [token]);

  useEffect(() => {
    if (hasAuthenticatedIdentityChanged(previousUserId.current, userId)) {
      queryClient.clear();
      previousUserId.current = userId;
    }
  }, [queryClient, userId]);

  return null;
}

function SessionExpiryHandler() {
  const { data: session } = useSession();

  useEffect(() => {
    if (session?.authError === "RefreshAccessTokenError") {
      void signOut({ redirectTo: "/login" });
    }
  }, [session?.authError]);

  return null;
}

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: { retry: 0 },
        },
      }),
  );

  return (
    <SessionProvider>
      <QueryClientProvider client={queryClient}>
        <ApiTokenBridge />
        <SessionExpiryHandler />
        {children}
      </QueryClientProvider>
    </SessionProvider>
  );
}
