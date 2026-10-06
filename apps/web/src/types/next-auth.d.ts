import "next-auth";

declare module "next-auth" {
  interface Session {
    supabaseAccessToken?: string;
    authError?: "RefreshAccessTokenError";
  }

  interface User {
    supabaseAccessToken?: string;
    supabaseRefreshToken?: string;
    supabaseExpiresAt?: number;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    supabaseAccessToken?: string;
    supabaseRefreshToken?: string;
    supabaseExpiresAt?: number;
    authError?: "RefreshAccessTokenError";
  }
}
