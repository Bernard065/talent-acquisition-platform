"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError("Please enter a valid developer JWT.");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      await login(token);
      router.push("/dashboard");
    } catch (err) {
      console.error("Login attempt failed:", err);
      setError("Failed to login with this token. Check your network or the token validity.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      
      {/* Mobile Branding (only shows on small screens since left pane is hidden) */}
      <div className="lg:hidden flex items-center gap-2 mb-8">
        <svg className="h-8 w-8 text-sr-green" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/></svg>
        <span className="font-display font-bold text-2xl tracking-tight text-sr-text-blue">MindHire</span>
      </div>

      <div className="flex flex-col gap-2 text-center lg:text-left mb-4">
        <h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">
          Developer Login
        </h1>
        <p className="text-sm text-sr-gray">
          Enter a valid developer JWT to authenticate against the local backend.
        </p>
      </div>

      <form onSubmit={handleLogin} className="flex flex-col gap-5">
        <div className="grid gap-2">
          <Label htmlFor="token">Bearer Token (JWT)</Label>
          <Input
            id="token"
            type="text"
            placeholder="eyJhbGciOiJSUzI1NiIs..."
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
            className="h-12"
          />
        </div>
        
        {error && <p className="text-sm text-red-500 font-medium">{error}</p>}

        <Button 
          type="submit" 
          disabled={isLoading}
          className="w-full bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white h-12 text-base font-semibold mt-2 transition-colors"
        >
          {isLoading ? "Signing in..." : "Sign In"}
        </Button>

        {/* Divider */}
        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-gray-200" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white px-2 text-sr-gray">
              Or continue with
            </span>
          </div>
        </div>

        {/* SSO Providers */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 opacity-50 pointer-events-none">
          <Button variant="outline" type="button" className="h-12 border-gray-200 hover:bg-gray-50 text-gray-900 hover:text-gray-900">
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
            </svg>
            Google
          </Button>
          <Button variant="outline" type="button" className="h-12 border-gray-200 hover:bg-gray-50 text-gray-900 hover:text-gray-900">
            <svg className="w-5 h-5 mr-2" viewBox="0 0 21 21">
              <path d="M10 0H0v10h10V0z" fill="#f25022"/>
              <path d="M21 0H11v10h10V0z" fill="#7fba00"/>
              <path d="M10 11H0v10h10V11z" fill="#00a4ef"/>
              <path d="M21 11H11v10h10V11z" fill="#ffb900"/>
            </svg>
            Microsoft
          </Button>
        </div>
      </form>

      <div className="text-center text-sm text-sr-gray mt-2">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="font-semibold text-sr-text-blue hover:text-sr-green hover:underline transition-colors">
          Sign up
        </Link>
      </div>
    </div>
  );
}
