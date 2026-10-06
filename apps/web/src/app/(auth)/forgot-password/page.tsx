"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/auth/password/forgot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const result = (await response.json()) as { message?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? "Couldn’t send a reset link.");
      setMessage(result.message ?? "Check your email for a password reset link.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn’t send a reset link. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="mb-2 text-center lg:text-left">
        <h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">Reset your password</h1>
        <p className="mt-2 text-sm text-sr-gray">Enter your work email and we’ll send you a reset link.</p>
      </div>

      <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
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
        {message && <p role="status" className="text-sm text-green-800">{message}</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <Button type="submit" disabled={isSubmitting} variant="secondary" className="h-12 w-full bg-sr-mint text-base font-semibold text-sr-text-blue hover:bg-sr-green hover:text-white">
          {isSubmitting ? "Sending link…" : "Send reset link"}
        </Button>
      </form>

      <p className="text-center text-sm text-sr-gray">
        Remember your password? <Link href="/login" className="font-semibold text-sr-text-blue hover:underline">Back to sign in</Link>
      </p>
    </div>
  );
}
