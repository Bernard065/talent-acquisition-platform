"use client";

import {
  createContext,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { authService } from "../lib/api/services";
import type { CurrentIdentityResponse } from "@/types/api";

interface AuthContextState {
  user: CurrentIdentityResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentIdentityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function initAuth() {
      try {
        setIsLoading(true);
        const identity = await authService.getCurrentIdentity();
        if (mounted) {
          setUser(identity);
        }
      } catch (err) {
        if (mounted) {
          setUser(null);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    initAuth();

    return () => {
      mounted = false;
    };
  }, []);

  const fetchIdentity = useCallback(async () => {
    try {
      setIsLoading(true);
      const identity = await authService.getCurrentIdentity();
      setUser(identity);
    } catch (err) {
      console.error("Failed to fetch user identity:", err);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = async (token: string) => {
    // In a real implementation, we would send the token to a Next.js API route
    // to set it as an httpOnly cookie.
    // For now, we simulate this by making a request to our internal route.
    try {
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      await fetchIdentity();
    } catch (err) {
      console.error("Login failed:", err);
      throw err;
    }
  };

  const logout = async () => {
    try {
      await fetch("/api/auth/session", { method: "DELETE" });
      setUser(null);
    } catch (err) {
      console.error("Logout failed:", err);
    }
  };

  const value: AuthContextState = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
