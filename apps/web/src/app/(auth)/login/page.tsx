"use client";

import React, { useState } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff, LoaderCircle, MindHireMark } from "@/components/icons";
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
        <MindHireMark className="h-8 w-8 text-sr-green" />
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
                <EyeOff className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Eye className="h-5 w-5" aria-hidden="true" />
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
            <LoaderCircle className="mr-2 h-5 w-5 animate-spin" aria-hidden="true" />
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
