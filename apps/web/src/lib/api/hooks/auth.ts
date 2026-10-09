"use client";

import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { getCurrentIdentity } from "../services/auth";

export const identityQueryKey = ["identity", "current"] as const;

export function useCurrentIdentity() {
  const { status } = useSession();

  return useQuery({
    queryKey: identityQueryKey,
    queryFn: ({ signal }) => getCurrentIdentity({ signal }),
    enabled: status === "authenticated",
    // Roles can change while a session is active (for example, after an admin
    // updates workspace membership). Refresh this authoritative identity when
    // a returning user focuses the app.
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}
