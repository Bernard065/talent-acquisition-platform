"use client";

import { useContext } from "react";
import { AuthContext } from "../providers/auth-provider";

/**
 * Hook to access the current authentication state and user identity.
 * Must be used within an AuthProvider.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  
  return context;
}
