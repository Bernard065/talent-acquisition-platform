"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useApprovalPolicyConfiguration,
  useCreateApprovalPolicy,
  useUpdateApprovalPolicyApprovers,
} from "@/lib/api/hooks/approvals";
import { ApiError } from "@/lib/api/errors";

export default function ApprovalSettingsPage() {
  const [name, setName] = useState("");
  const [approverIds, setApproverIds] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const configurationQuery = useApprovalPolicyConfiguration();
  const createPolicy = useCreateApprovalPolicy();
  const updateApprovers = useUpdateApprovalPolicyApprovers();
  const configuration = configurationQuery.data;
  const selectableApprovers = configuration?.available_approvers.filter(
    (approver) => !approver.is_current_user,
  ) ?? [];
  const defaultSelectableApproverIds = configuration?.default_approver_user_ids.filter(
    (userId) => selectableApprovers.some((approver) => approver.id === userId),
  ) ?? [];
  const selectedApproverIds = approverIds ?? defaultSelectableApproverIds;
  const isBusy = createPolicy.isPending || updateApprovers.isPending;
  const isForbidden =
    configurationQuery.error instanceof ApiError &&
    configurationQuery.error.isForbidden;

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (selectedApproverIds.length === 0) {
      setError("Choose at least one approver.");
      return;
    }

    try {
      if (configuration?.default_policy) {
        await updateApprovers.mutateAsync({
          policyId: configuration.default_policy.id,
          approvers: { approver_user_ids: selectedApproverIds },
          idempotencyKey: crypto.randomUUID(),
        });
        setNotice("Default policy approvers updated for future requisitions.");
      } else {
        await createPolicy.mutateAsync({
          policy: {
            name: name.trim(),
            approver_user_ids: selectedApproverIds,
            is_default: true,
          },
          idempotencyKey: crypto.randomUUID(),
        });
        setName("");
        setNotice("The default approval policy is ready for future requisitions.");
      }
      setApproverIds(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the approval policy.");
    }
  }

  function toggleApprover(userId: string, selected: boolean) {
    setApproverIds((current) => {
      const selection = current ?? defaultSelectableApproverIds;
      if (selected) {
        return selection.includes(userId) || selection.length >= 20
          ? selection
          : [...selection, userId];
      }
      return selection.filter((id) => id !== userId);
    });
  }

  const assignedApproverNames = configuration?.default_approver_user_ids
    .map((userId) => configuration.available_approvers.find((member) => member.id === userId)?.display_name)
    .filter((displayName): displayName is string => Boolean(displayName)) ?? [];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header>
        <Link href="/dashboard/requisitions" className="text-sm font-medium text-sr-green hover:underline">
          ← Requisitions
        </Link>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-sr-text-blue">Approval settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Choose who reviews requisitions submitted for approval. Reviewers act in the order selected.
        </p>
      </header>

      {configurationQuery.isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500" aria-live="polite">
          Loading approval settings…
        </div>
      ) : configurationQuery.isError ? (
        isForbidden ? (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-6">
            <h2 className="font-semibold text-amber-950">Workspace admin access required</h2>
            <p role="alert" className="mt-2 text-sm text-amber-900">
              Approval settings are available to workspace admins. Contact your workspace admin if you need a change.
            </p>
          </section>
        ) : (
          <section className="rounded-xl border border-red-200 bg-red-50 p-6">
            <p role="alert" className="text-sm text-red-800">
              We couldn’t load approval settings. Please try again.
            </p>
            <Button className="mt-4" variant="outline" onClick={() => void configurationQuery.refetch()}>
              Try again
            </Button>
          </section>
        )
      ) : configuration ? (
        <>
          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-sr-text-blue">Current default policy</h2>
            {configuration.default_policy ? (
              <div className="mt-3 rounded-lg bg-gray-50 p-4">
                <p className="font-medium text-gray-900">{configuration.default_policy.name}</p>
                <p className="mt-1 text-sm text-gray-600">
                  {assignedApproverNames.length
                    ? assignedApproverNames.join(" → ")
                    : "No approvers are assigned."}
                </p>
                <p className="mt-2 text-xs text-gray-500">
                  New submissions use this policy. Existing approval requests keep their original reviewers.
                </p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-gray-600">
                No default policy is configured. Create one before submitting a requisition for approval.
              </p>
            )}
          </section>

          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-sr-text-blue">
              {configuration.default_policy ? "Update current default policy" : "Create the default policy"}
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              {configuration.default_policy
                ? "Changes apply to future submissions. Existing approval requests keep their original reviewer list."
                : "Creating this policy makes it the default for future submissions. Choose a unique name."}
            </p>
            <form onSubmit={savePolicy} className="mt-5 grid gap-5">
              {!configuration.default_policy && (
                <div className="grid gap-2">
                  <Label htmlFor="approval-policy-name">Policy name</Label>
                  <Input
                    id="approval-policy-name"
                    required
                    maxLength={200}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="e.g. Hiring approval 2026"
                  />
                </div>
              )}

              <fieldset className="grid gap-3">
                <legend className="text-sm font-medium text-gray-800">Approvers</legend>
                <p className="text-xs text-gray-500">
                  Select up to 20 approvers. Their approval steps follow the order you select them.
                  Your account is omitted to prevent you from approving a policy you create.
                </p>
                {selectableApprovers.length ? (
                  <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
                    {selectableApprovers.map((approver) => (
                      <li key={approver.id} className="flex items-start gap-3 p-3">
                        <input
                          id={`approver-${approver.id}`}
                          type="checkbox"
                          checked={selectedApproverIds.includes(approver.id)}
                          onChange={(event) => toggleApprover(approver.id, event.target.checked)}
                          disabled={isBusy || (
                            selectedApproverIds.length >= 20 && !selectedApproverIds.includes(approver.id)
                          )}
                          className="mt-1 h-4 w-4 rounded border-gray-300 text-sr-green focus:ring-sr-green"
                        />
                        <label htmlFor={`approver-${approver.id}`} className="min-w-0 cursor-pointer">
                          <span className="block text-sm font-medium text-gray-900">{approver.display_name}</span>
                          <span className="block text-sm text-gray-500">{approver.email}</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
                    No other workspace members are available. Invite a teammate and have them accept the invitation before assigning them as an approver.
                    {" "}
                    <Link href="/dashboard/team" className="font-semibold underline">
                      Go to Team
                    </Link>
                  </p>
                )}
                {selectedApproverIds.length > 0 && (
                  <p className="text-xs text-gray-500" aria-live="polite">
                    Approval order: {selectedApproverIds
                      .map((userId) => configuration.available_approvers.find((member) => member.id === userId)?.display_name)
                      .filter(Boolean)
                      .join(" → ")}
                  </p>
                )}
              </fieldset>

              {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
              {notice && <p role="status" className="text-sm text-green-800">{notice}</p>}
              <div>
                <Button type="submit" disabled={isBusy || selectableApprovers.length === 0}>
                  {isBusy ? "Saving policy…" : configuration.default_policy ? "Update approvers" : "Save as default policy"}
                </Button>
              </div>
            </form>
          </section>
        </>
      ) : null}
    </div>
  );
}
