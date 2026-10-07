"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function PasswordVisibilityToggle({
  visible,
  label,
  onToggle,
}: {
  visible: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={`${visible ? "Hide" : "Show"} ${label}`}
      aria-pressed={visible}
      className="absolute right-3 top-1/2 -translate-y-1/2 rounded-sm text-gray-400 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sr-green"
    >
      {visible ? (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
        </svg>
      ) : (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      )}
    </button>
  );
}

export function AcceptInvitationForm({ tokenHash }: { tokenHash: string | null }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null);
    if (!tokenHash) { setError("This invitation link is incomplete or expired. Ask your workspace administrator for a new invitation."); return; }
    if (password !== confirmation) { setError("The passwords don’t match."); return; }
    setIsSubmitting(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/workspace-invitations/accept`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_hash: tokenHash, password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail ?? "Could not accept this invitation.");
      }
      router.replace("/login?invitation=accepted");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not accept this invitation. Please try again.");
    } finally { setIsSubmitting(false); }
  }

  return <div className="flex flex-col gap-6">
    <div className="text-center lg:text-left"><h1 className="text-3xl font-semibold tracking-tight text-sr-text-blue">Join your hiring workspace</h1><p className="mt-2 text-sm text-sr-gray">Set a password to finish creating your account.</p></div>
    <form onSubmit={submit} className="flex flex-col gap-5">
      <div className="grid gap-2">
        <Label htmlFor="password">Create password</Label>
        <div className="relative">
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            minLength={8}
            required
            className="h-12 pr-12"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <PasswordVisibilityToggle
            visible={showPassword}
            label="password"
            onToggle={() => setShowPassword((visible) => !visible)}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="confirmation">Confirm password</Label>
        <div className="relative">
          <Input
            id="confirmation"
            type={showConfirmation ? "text" : "password"}
            autoComplete="new-password"
            minLength={8}
            required
            className="h-12 pr-12"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
          <PasswordVisibilityToggle
            visible={showConfirmation}
            label="password confirmation"
            onToggle={() => setShowConfirmation((visible) => !visible)}
          />
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <Button type="submit" disabled={isSubmitting} variant="secondary" className="h-12 w-full bg-sr-mint text-base font-semibold text-sr-text-blue hover:bg-sr-green hover:text-white">{isSubmitting ? "Setting up account…" : "Accept invitation"}</Button>
    </form>
    <p className="text-center text-sm text-sr-gray">Already set up? <Link href="/login" className="font-semibold text-sr-text-blue hover:underline">Go to sign in</Link></p>
  </div>;
}
