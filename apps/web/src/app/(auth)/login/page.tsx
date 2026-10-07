"use client";

import React, { useState } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    let isNavigating = false;

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (!result || result.error) {
        setError("We couldn’t sign you in. Check your details and try again.");
        return;
      }

      isNavigating = true;
      router.push("/dashboard");
      router.refresh();
    } catch {
      setError("Sign-in is temporarily unavailable. Please try again shortly.");
    } finally {
      if (!isNavigating) setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      
      {/* Mobile Branding (only shows on small screens since left pane is hidden) */}
      <div className="lg:hidden flex items-center gap-2 mb-8">
        <svg className="h-8 w-8 text-sr-green" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/></svg>
        <span className="font-display font-bold text-2xl tracking-tight text-sr-text-blue">MindHire</span>
      </div>

      <div className="flex flex-col gap-2 text-center lg:text-left mb-4">
        <h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">
          Welcome back
        </h1>
        <p className="text-sm text-sr-gray">
          Enter your details below to log into your account
        </p>
      </div>

      <form className="flex flex-col gap-5" onSubmit={handleSubmit} aria-busy={isSubmitting}>
        <div className="grid gap-2">
          <Label htmlFor="email">Work Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            required
            className="h-12"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link href="/forgot-password" className="text-sm text-sr-text-blue hover:underline">
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <Input 
              id="password" 
              type={showPassword ? "text" : "password"} 
              autoComplete="current-password"
              required 
              className="h-12 pr-10"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none"
            >
              {showPassword ? (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
        </div>
        
        {error && (
          <p role="alert" className="text-sm text-red-700" aria-live="polite">
            {error}
          </p>
        )}

        <Button 
          type="submit" 
          disabled={isSubmitting}
          aria-busy={isSubmitting}
          variant="secondary"
          className="w-full bg-sr-mint hover:bg-sr-green text-sr-text-blue hover:text-white h-12 text-base font-semibold mt-2 transition-colors"
        >
          {isSubmitting && (
            <svg
              className="mr-2 h-5 w-5 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          )}
          {isSubmitting ? "Signing in…" : "Sign In"}
        </Button>
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
