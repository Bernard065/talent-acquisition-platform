"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff } from "@/components/icons";
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
        <EyeOff className="h-5 w-5" aria-hidden="true" />
      ) : (
        <Eye className="h-5 w-5" aria-hidden="true" />
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
