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
  });
}
