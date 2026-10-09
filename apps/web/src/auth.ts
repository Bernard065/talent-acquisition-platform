import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import type { JWT } from "next-auth/jwt";
import { Buffer } from "node:buffer";
import type { Role } from "@/types/api/auth";

const supabaseUrl = process.env.SUPABASE_URL;
const supabasePublishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;

type SupabaseTokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: {
    id: string;
    email?: string;
    app_metadata?: { roles?: unknown };
    user_metadata?: { full_name?: string; name?: string; given_name?: string };
  };
};

const workspaceRoles = [
  "tenant_admin",
  "recruiter",
  "hiring_manager",
  "interviewer",
  "people_operations",
  "analyst",
] as const satisfies readonly Role[];

function normalizeWorkspaceRoles(roles: unknown): Role[] {
  if (!Array.isArray(roles)) return [];

  return roles.filter((role): role is Role =>
    workspaceRoles.includes(role as Role),
  );
}

function getWorkspaceRoles(user: SupabaseTokenResponse["user"]): Role[] {
  return normalizeWorkspaceRoles(user.app_metadata?.roles);
}

function getWorkspaceRolesFromAccessToken(accessToken?: string): Role[] {
  const payload = accessToken?.split(".")[1];
  if (!payload) return [];

  try {
    // This claim is only used to render navigation; the API verifies the token
    // independently before authorizing protected operations.
    const claims = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    ) as { app_metadata?: { roles?: unknown } };
    return normalizeWorkspaceRoles(claims.app_metadata?.roles);
  } catch {
    return [];
  }
}

function getUserDisplayName(user: SupabaseTokenResponse["user"]): string | undefined {
  const metadataName =
    user.user_metadata?.full_name?.trim() ||
    user.user_metadata?.name?.trim() ||
    user.user_metadata?.given_name?.trim();
  if (metadataName) return metadataName;

  const emailName = user.email?.split("@", 1)[0]?.trim();
  if (!emailName) return undefined;

  return emailName
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(" ");
}

type AuthToken = JWT;

async function requestSupabaseToken(
  grant: "password" | "refresh_token",
  credentials: Record<string, string>,
): Promise<SupabaseTokenResponse | null> {
  if (!supabaseUrl || !supabasePublishableKey) return null;

  const response = await fetch(
    `${supabaseUrl.replace(/\/$/, "")}/auth/v1/token?grant_type=${grant}`,
    {
      method: "POST",
      headers: {
        apikey: supabasePublishableKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(credentials),
      cache: "no-store",
    },
  );

  if (!response.ok) return null;
  return (await response.json()) as SupabaseTokenResponse;
}

async function refreshSupabaseToken(token: AuthToken): Promise<AuthToken> {
  if (!token.supabaseRefreshToken) {
    return {
      ...token,
      supabaseAccessToken: undefined,
      authError: "RefreshAccessTokenError",
    };
  }

  try {
    const refreshed = await requestSupabaseToken("refresh_token", {
      refresh_token: token.supabaseRefreshToken,
    });
    if (!refreshed) throw new Error("Supabase token refresh failed");

    return {
      ...token,
      supabaseAccessToken: refreshed.access_token,
      supabaseRefreshToken: refreshed.refresh_token,
      supabaseExpiresAt: Date.now() + refreshed.expires_in * 1000,
      roles: getWorkspaceRoles(refreshed.user),
      authError: undefined,
    };
  } catch {
    return {
      ...token,
      supabaseAccessToken: undefined,
      authError: "RefreshAccessTokenError",
    };
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email;
        const password = credentials?.password;
        if (typeof email !== "string" || typeof password !== "string") return null;

        const result = await requestSupabaseToken("password", {
          email: email.trim(),
          password,
        });
        if (!result?.user?.id) return null;

        return {
          id: result.user.id,
          email: result.user.email,
          name: getUserDisplayName(result.user),
          supabaseAccessToken: result.access_token,
          supabaseRefreshToken: result.refresh_token,
          supabaseExpiresAt: Date.now() + result.expires_in * 1000,
          roles: getWorkspaceRoles(result.user),
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      const authToken = token as AuthToken;
      if (user) {
        return {
          ...authToken,
          sub: user.id,
          supabaseAccessToken: user.supabaseAccessToken,
          supabaseRefreshToken: user.supabaseRefreshToken,
          supabaseExpiresAt: user.supabaseExpiresAt,
          roles: user.roles,
          authError: undefined,
        };
      }

      if (authToken.authError === "RefreshAccessTokenError") {
        return authToken;
      }

      if (
        authToken.supabaseAccessToken &&
        authToken.supabaseExpiresAt &&
        Date.now() < authToken.supabaseExpiresAt - 60_000
      ) {
        return {
          ...authToken,
          roles: authToken.roles ?? getWorkspaceRolesFromAccessToken(authToken.supabaseAccessToken),
        };
      }

      return refreshSupabaseToken(authToken);
    },
    async session({ session, token }) {
      const authToken = token as AuthToken;
      if (session.user && authToken.sub) {
        session.user.id = authToken.sub;
      }
      session.supabaseAccessToken = authToken.supabaseAccessToken;
      session.roles = authToken.roles;
      session.authError = authToken.authError;
      return session;
    },
  },
});
