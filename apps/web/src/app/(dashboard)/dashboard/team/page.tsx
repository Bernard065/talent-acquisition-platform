"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { del, get, post } from "@/lib/api/client";

type TeamRole = "recruiter" | "hiring_manager" | "interviewer" | "people_operations" | "analyst";
type Invitation = { id: string; email: string; role: TeamRole | "tenant_admin"; status: string; created_at: string; expires_at: string };

const roleNames: Record<TeamRole | "tenant_admin", string> = {
  tenant_admin: "Workspace admin", recruiter: "Recruiter", hiring_manager: "Hiring manager",
  interviewer: "Interviewer", people_operations: "People operations", analyst: "Analyst",
};

export default function TeamPage() {
  const { status } = useSession();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TeamRole>("recruiter");
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setInvitations(await get<Invitation[]>("/team/invitations")); }
    catch { setError("You need workspace admin access to manage invitations, or the list could not be loaded."); }
  }, []);

  useEffect(() => {
    if (status !== "authenticated") return;
    let current = true;
    get<Invitation[]>("/team/invitations")
      .then((result) => { if (current) setInvitations(result); })
      .catch(() => { if (current) setError("You need workspace admin access to manage invitations, or the list could not be loaded."); });
    return () => { current = false; };
  }, [status]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setNotice(null);
    try {
      await post<Invitation>("/team/invitations", { email, role });
      setEmail(""); setNotice("Invitation sent. The link expires in one hour."); await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not send invitation.");
    } finally { setBusy(false); }
  }

  async function revoke(id: string) {
    setBusy(true); setError(null);
    try { await del(`/team/invitations/${id}`); await load(); }
    catch { setError("Could not revoke this invitation. Please try again."); }
    finally { setBusy(false); }
  }

  return <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
    <header><h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Team</h1>
      <p className="mt-1 text-sm text-gray-500">Invite people into your hiring workspace and choose their access.</p></header>
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-sr-text-blue">Invite a teammate</h2>
      <form onSubmit={invite} className="mt-5 grid gap-4 sm:grid-cols-[1fr_220px_auto] sm:items-end">
        <div className="grid gap-2"><Label htmlFor="invite-email">Work email</Label><Input id="invite-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" /></div>
        <div className="grid gap-2"><Label htmlFor="invite-role">Role</Label><select id="invite-role" className="h-10 rounded-md border border-gray-300 bg-white px-3 text-sm" value={role} onChange={(event) => setRole(event.target.value as TeamRole)}>{Object.entries(roleNames).filter(([key]) => key !== "tenant_admin").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
        <Button type="submit" disabled={busy} variant="secondary" className="h-10 bg-sr-mint font-semibold text-sr-text-blue hover:bg-sr-green hover:text-white">{busy ? "Sending…" : "Send invitation"}</Button>
      </form>
      {notice && <p role="status" className="mt-4 text-sm text-green-800">{notice}</p>}
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    </section>
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-sr-text-blue">Invitations</h2>
      {invitations.length === 0 ? <p className="mt-4 text-sm text-gray-500">No invitations have been sent yet.</p> : <ul className="mt-4 divide-y divide-gray-100">{invitations.map((item) => <li key={item.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium text-sr-text-blue">{item.email}</p><p className="mt-1 text-sm text-gray-500">{roleNames[item.role]} · {item.status} · expires {new Date(item.expires_at).toLocaleDateString()}</p></div>{item.status === "pending" && <Button type="button" disabled={busy} onClick={() => void revoke(item.id)} className="self-start bg-white text-sm text-red-700 hover:bg-red-50">Revoke</Button>}</li>)}</ul>}
    </section>
  </div>;
}
