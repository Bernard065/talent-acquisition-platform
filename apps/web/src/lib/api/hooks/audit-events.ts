"use client";

import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { listAuditEvents } from "../services/audit-events";
import type { AuditEventSearchParams } from "@/types/api/audit-events";

export const auditEventQueryKeys = {
  all: ["audit-events"] as const,
  list: (params: AuditEventSearchParams) =>
    [...auditEventQueryKeys.all, params] as const,
};

export function useAuditEvents(params: AuditEventSearchParams) {
  const { status } = useSession();

  return useQuery({
    queryKey: auditEventQueryKeys.list(params),
    queryFn: ({ signal }) => listAuditEvents(params, { signal }),
    enabled: status === "authenticated",
  });
}
