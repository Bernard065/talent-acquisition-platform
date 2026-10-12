"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useCreateTeamInvitation,
  useGrantTeamMemberInterviewerRole,
  useRevokeTeamInvitation,
  useTeamInterviewers,
  useTeamInvitations,
  useWorkspaceMembers,
} from "@/lib/api/hooks/team";
import type { TeamInvitation, TeamRole } from "@/types/api/team";

const roleNames: Record<TeamRole | "tenant_admin", string> = {
  tenant_admin: "Workspace admin", recruiter: "Recruiter", hiring_manager: "Hiring manager",
  interviewer: "Interviewer", people_operations: "People operations", analyst: "Analyst",
};

export default function TeamPage() {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Exclude<TeamRole, "tenant_admin">>("recruiter");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const invitationsQuery = useTeamInvitations();
  const membersQuery = useWorkspaceMembers();
  const interviewersQuery = useTeamInterviewers();
  const createInvitation = useCreateTeamInvitation();
  const grantInterviewerRole = useGrantTeamMemberInterviewerRole();
  const revokeInvitation = useRevokeTeamInvitation();
  const invitations = invitationsQuery.data ?? [];
  const busy = createInvitation.isPending || revokeInvitation.isPending;
  const [memberIdToPromote, setMemberIdToPromote] = useState("");
  const interviewerIds = new Set(interviewersQuery.data?.items.map((item) => item.id) ?? []);
  const eligibleMembers = membersQuery.data?.items.filter((item) => !interviewerIds.has(item.id)) ?? [];
  const listError = invitationsQuery.isError
    ? "You need workspace admin access to manage invitations, or the list could not be loaded."
    : null;

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      await createInvitation.mutateAsync({ request: { email, role } });
      setEmail("");
      setNotice("Invitation sent. The link expires in one hour.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not send invitation.");
    }
  }

  async function revoke(id: string) {
    setError(null);
    setNotice(null);
    try {
      await revokeInvitation.mutateAsync(id);
    } catch {
      setError("Could not revoke this invitation. Please try again.");
    }
  }

  return <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
    <header><h1 className="text-2xl font-bold tracking-tight text-sr-text-blue">Team</h1>
      <p className="mt-1 text-sm text-gray-500">Invite people into your hiring workspace and choose their access.</p></header>
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-sr-text-blue">Invite a teammate</h2>
      <form onSubmit={invite} className="mt-5 grid gap-4 sm:grid-cols-[1fr_220px_auto] sm:items-end">
        <div className="grid gap-2"><Label htmlFor="invite-email">Work email</Label><Input id="invite-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" /></div>
        <div className="grid gap-2"><Label htmlFor="invite-role">Role</Label><select id="invite-role" className="h-10 rounded-md border border-gray-300 bg-white px-3 text-sm" value={role} onChange={(event) => setRole(event.target.value as Exclude<TeamRole, "tenant_admin">)}>{Object.entries(roleNames).filter(([key]) => key !== "tenant_admin").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
        <Button type="submit" disabled={busy} variant="secondary" className="h-10 bg-sr-mint font-semibold text-sr-text-blue hover:bg-sr-green hover:text-white">{busy ? "Sending…" : "Send invitation"}</Button>
      </form>
      {notice && <p role="status" className="mt-4 text-sm text-green-800">{notice}</p>}
      {(error || listError) && <p role="alert" className="mt-4 text-sm text-red-700">{error ?? listError}</p>}
    </section>
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-sr-text-blue">Add interviewer access</h2>
      <p className="mt-1 text-sm text-gray-600">Give any existing workspace teammate interviewer access without sending another invitation. Their current role stays in place. They should sign out and back in to refresh their access.</p>
      {membersQuery.isLoading || interviewersQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" role="status">Loading workspace teammates…</p>
      ) : membersQuery.isError || interviewersQuery.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3" role="alert">
          <p className="text-sm text-red-700">We couldn’t load teammates and their interviewer access.</p>
          <Button type="button" variant="outline" onClick={() => { void membersQuery.refetch(); void interviewersQuery.refetch(); }}>Try again</Button>
        </div>
      ) : eligibleMembers.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600">Every workspace teammate already has interviewer access, or no members are available.</p>
      ) : (
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="grid flex-1 gap-2">
            <Label htmlFor="interviewer-member">Existing teammate</Label>
            <select id="interviewer-member" className="h-10 rounded-md border border-gray-300 bg-white px-3 text-sm" value={memberIdToPromote} onChange={(event) => setMemberIdToPromote(event.target.value)}>
              <option value="">Select a teammate</option>
              {eligibleMembers.map((member) => <option key={member.id} value={member.id}>{member.display_name} · {member.email}</option>)}
            </select>
          </div>
          <Button
            type="button"
            variant="secondary"
            disabled={!memberIdToPromote || grantInterviewerRole.isPending}
            onClick={async () => {
              setError(null);
              setNotice(null);
              try {
                await grantInterviewerRole.mutateAsync(memberIdToPromote);
                setMemberIdToPromote("");
                setNotice("Interviewer access added. They are now available when scheduling. Ask them to sign out and back in to activate interviewer permissions.");
              } catch {
                setError("Could not add interviewer access. Refresh the team list and try again.");
              }
            }}
          >
            {grantInterviewerRole.isPending ? "Adding…" : "Add interviewer access"}
          </Button>
        </div>
      )}
    </section>
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-sr-text-blue">Invitations</h2>
      {invitationsQuery.isLoading ? (
        <p className="mt-4 text-sm text-gray-500" aria-live="polite">Loading invitations…</p>
      ) : invitationsQuery.isError ? (
        <Button className="mt-4" variant="outline" onClick={() => void invitationsQuery.refetch()}>
          Try again
        </Button>
      ) : invitations.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">No invitations have been sent yet.</p>
      ) : (
        <ul className="mt-4 divide-y divide-gray-100">
          {invitations.map((item: TeamInvitation) => (
            <li key={item.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-medium text-sr-text-blue">{item.email}</p>
                <p className="mt-1 text-sm text-gray-500">
                  {roleNames[item.role]} · {item.status} · expires {new Date(item.expires_at).toLocaleDateString()}
                </p>
              </div>
              {item.status === "pending" && (
                <Button
                  type="button"
                  disabled={busy}
                  onClick={() => void revoke(item.id)}
                  className="self-start bg-white text-sm text-red-700 hover:bg-red-50"
                >Revoke</Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  </div>;
}
