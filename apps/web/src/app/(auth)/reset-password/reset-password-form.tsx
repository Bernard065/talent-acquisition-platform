"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ResetPasswordForm({ tokenHash }: { tokenHash: string | null }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!tokenHash) {
      setError("This reset link is incomplete or expired. Request a new one.");
      return;
    }
    if (password !== confirmation) {
      setError("The passwords don’t match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokenHash, password }),
      });
      const result = (await response.json()) as { message?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? "Couldn’t update the password.");
      setSuccess(true);
      window.setTimeout(() => router.replace("/login"), 1800);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn’t update the password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="mb-2 text-center lg:text-left">
        <h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">Choose a new password</h1>
        <p className="mt-2 text-sm text-sr-gray">Use at least 8 characters for your new password.</p>
      </div>

      {success ? (
        <div className="space-y-4 text-center lg:text-left">
          <p role="status" className="text-sm text-green-800">Your password has been updated. Redirecting you to sign in…</p>
          <Link href="/login" className="text-sm font-semibold text-sr-text-blue hover:underline">Go to sign in</Link>
        </div>
      ) : (
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-2">
            <Label htmlFor="password">New password</Label>
            <Input id="password" type="password" autoComplete="new-password" minLength={8} required className="h-12" value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="confirmation">Confirm new password</Label>
            <Input id="confirmation" type="password" autoComplete="new-password" minLength={8} required className="h-12" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <Button type="submit" disabled={isSubmitting} variant="secondary" className="h-12 w-full bg-sr-mint text-base font-semibold text-sr-text-blue hover:bg-sr-green hover:text-white">
            {isSubmitting ? "Updating password…" : "Update password"}
          </Button>
        </form>
      )}
      {!success && <p className="text-center text-sm text-sr-gray">Need another link? <Link href="/forgot-password" className="font-semibold text-sr-text-blue hover:underline">Request a reset</Link></p>}
    </div>
  );
}
