import type { Role } from "@/types/api/auth";

export function hasAuthenticatedIdentityChanged(
  previousUserId: string | null,
  currentUserId: string | null,
): boolean {
  return previousUserId !== currentUserId;
}

export function getAuthorizationContext(
  userId: string | null | undefined,
  roles: readonly Role[] | undefined,
  tenantId?: string | null,
): string | null {
  if (!userId) return null;
  return `${tenantId ?? ""}:${userId}:${[...(roles ?? [])].sort().join(",")}`;
}
