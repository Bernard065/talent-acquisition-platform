import "next-auth";
import type { DefaultSession } from "next-auth";
import type { Role } from "@/types/api/auth";

declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & { id?: string };
    supabaseAccessToken?: string;
    authError?: "RefreshAccessTokenError";
    roles?: Role[];
  }

  interface User {
    supabaseAccessToken?: string;
    supabaseRefreshToken?: string;
    supabaseExpiresAt?: number;
    roles?: Role[];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    supabaseAccessToken?: string;
    supabaseRefreshToken?: string;
    supabaseExpiresAt?: number;
    roles?: Role[];
    authError?: "RefreshAccessTokenError";
  }
}
