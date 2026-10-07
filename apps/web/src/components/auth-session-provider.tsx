"use client";

import { SessionProvider, signOut, useSession } from "next-auth/react";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { setTokenAccessor } from "@/lib/api";

function ApiTokenBridge() {
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  const previousToken = useRef<string | null>(null);

  useEffect(() => {
    const token = session?.supabaseAccessToken ?? null;
    setTokenAccessor(() => token);
    if (previousToken.current !== token) {
      queryClient.clear();
      previousToken.current = token;
    }
    if (session?.authError) void signOut({ redirectTo: "/login" });
  }, [queryClient, session?.authError, session?.supabaseAccessToken]);

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
        {children}
      </QueryClientProvider>
    </SessionProvider>
  );
}
