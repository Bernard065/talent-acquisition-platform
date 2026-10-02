import type { Role } from "@/types/api";

/** Standard claims present in our platform's JWTs. */
export interface TokenClaims {
  sub: string;
  tenant_id: string;
  roles: Role[];
  exp: number;
  iat: number;
  iss: string;
  aud: string;
}

/**
 * Parses a JWT payload without verifying the signature.
 * (Signature verification happens on the backend).
 */
export function decodeJwt(token: string): TokenClaims | null {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;

    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );

    return JSON.parse(jsonPayload) as TokenClaims;
  } catch (error) {
    console.error("Failed to decode JWT:", error);
    return null;
  }
}

/**
 * Checks if a JWT is expired (with a 60-second leeway).
 */
export function isTokenExpired(token: string): boolean {
  const claims = decodeJwt(token);
  if (!claims) return true;

  // Add 60s leeway to proactively refresh before actual expiry
  const now = Math.floor(Date.now() / 1000);
  return claims.exp - 60 < now;
}
