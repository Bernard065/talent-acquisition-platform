"use client";

import { useState, type FormEvent } from "react";
import { KeyRound, Pencil, Plus, RefreshCw, RotateCw, X } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import {
  useCreateWebhookEndpoint,
  useDeleteWebhookEndpoint,
  useDisableWebhookEndpoint,
  useRotateWebhookEndpointSecret,
  useUpdateWebhookEndpoint,
  useWebhookEndpoints,
} from "@/lib/api/hooks/webhook-endpoints";
import type { WebhookEndpoint } from "@/types/api/webhook-endpoints";

type WebhookDraft = {
  name: string;
  url: string;
  eventTypes: string;
};

const EMPTY_DRAFT: WebhookDraft = { name: "", url: "", eventTypes: "" };

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function parseEventTypes(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((eventType) => eventType.trim()).filter(Boolean))];
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

export function WebhookIntegrationsPanel() {
  const endpointsQuery = useWebhookEndpoints();
  const createEndpoint = useCreateWebhookEndpoint();
  const updateEndpoint = useUpdateWebhookEndpoint();
  const rotateSecret = useRotateWebhookEndpointSecret();
  const disableEndpoint = useDisableWebhookEndpoint();
  const retireEndpoint = useDeleteWebhookEndpoint();
  const [draft, setDraft] = useState<WebhookDraft>(EMPTY_DRAFT);
  const [editingEndpoint, setEditingEndpoint] = useState<WebhookEndpoint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const isSaving = createEndpoint.isPending || updateEndpoint.isPending;
  const isManaging =
    rotateSecret.isPending || disableEndpoint.isPending || retireEndpoint.isPending;
  const endpoints = endpointsQuery.data?.items ?? [];

  function resetForm() {
    setDraft(EMPTY_DRAFT);
    setEditingEndpoint(null);
  }

  function startEditing(endpoint: WebhookEndpoint) {
    setEditingEndpoint(endpoint);
    setDraft({
      name: endpoint.name,
      url: endpoint.url,
      eventTypes: endpoint.event_types.join("\n"),
    });
    setError(null);
    setNotice(null);
    document.getElementById("webhook-endpoint-name")?.focus();
  }

  async function saveEndpoint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const eventTypes = parseEventTypes(draft.eventTypes);
    if (eventTypes.length === 0) {
      setError("Add at least one event type to subscribe to.");
      return;
    }

    const request = {
      name: draft.name.trim(),
      url: draft.url.trim(),
      event_types: eventTypes,
    };

    try {
      if (editingEndpoint) {
        await updateEndpoint.mutateAsync({
          endpointId: editingEndpoint.id,
          request: { ...request, expected_version: editingEndpoint.version },
          idempotencyKey: crypto.randomUUID(),
        });
        setNotice("Webhook endpoint updated.");
      } else {
        await createEndpoint.mutateAsync({
          request,
          idempotencyKey: crypto.randomUUID(),
        });
        setNotice("Webhook endpoint created.");
      }
      resetForm();
    } catch (cause) {
      setError(getErrorMessage(cause, "Could not save this webhook endpoint."));
    }
  }

  async function rotateEndpointSecret(endpoint: WebhookEndpoint) {
    if (!window.confirm(
      `Replace the signing secret for ${endpoint.name}? MindHire will not display the new value. Confirm that your receiving system can access the configured secret vault before continuing.`,
    )) return;

    setError(null);
    setNotice(null);
    try {
      await rotateSecret.mutateAsync({
        endpointId: endpoint.id,
        request: { expected_version: endpoint.version },
        idempotencyKey: crypto.randomUUID(),
      });
      setNotice(`Signing secret rotated for ${endpoint.name}. Update the receiver through your secret-vault setup.`);
    } catch (cause) {
      setError(getErrorMessage(cause, "Could not rotate the signing secret."));
    }
  }

  async function disableEndpointNow(endpoint: WebhookEndpoint) {
    if (!window.confirm(
      `Disable ${endpoint.name}? MindHire will stop sending future events to this endpoint.`,
    )) return;

    setError(null);
    setNotice(null);
    try {
      await disableEndpoint.mutateAsync({
        endpointId: endpoint.id,
        request: { expected_version: endpoint.version },
        idempotencyKey: crypto.randomUUID(),
      });
      setNotice(`${endpoint.name} has been disabled.`);
    } catch (cause) {
      setError(getErrorMessage(cause, "Could not disable this endpoint."));
    }
  }

  async function retireEndpointNow(endpoint: WebhookEndpoint) {
    if (!window.confirm(
      `Retire ${endpoint.name}? The endpoint will be disabled and removed from this list. Its audit history will remain, and the configured vault will attempt to remove its signing key.`,
    )) return;

    setError(null);
    setNotice(null);
    try {
      await retireEndpoint.mutateAsync({
        endpointId: endpoint.id,
        request: { expected_version: endpoint.version },
        idempotencyKey: crypto.randomUUID(),
      });
      setNotice(
        `${endpoint.name} has been retired and removed from active settings. The configured vault was asked to remove its signing key; verify in the vault if you need to confirm cleanup.`,
      );
    } catch (cause) {
      setError(getErrorMessage(cause, "Could not revoke this endpoint's signing key."));
    }
  }

  return (
    <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-bold text-gray-900">Workspace webhooks</h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-gray-600">
            Configure HTTPS destinations for workspace event subscriptions. Destination hosts
            must be allowed by the API operator, and signing secrets remain in the configured vault.
          </p>
        </div>
        <span className="inline-flex w-fit items-center rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-800">
          Workspace admin
        </span>
      </header>

      <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-relaxed text-amber-950">
        MindHire currently has no business workflows publishing events to this delivery pipeline,
        so these subscriptions will not receive events yet. Delivery attempts and response history
        are also not available in this settings screen.
      </div>

      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

      <form onSubmit={(event) => void saveEndpoint(event)} className="mt-5 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-gray-900">
            {editingEndpoint ? "Edit webhook endpoint" : "Add webhook endpoint"}
          </h3>
          {editingEndpoint && (
            <button
              type="button"
              onClick={resetForm}
              className="inline-flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-gray-900"
            >
              <X aria-hidden="true" className="h-4 w-4" /> Cancel edit
            </button>
          )}
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
            Endpoint name
            <input
              id="webhook-endpoint-name"
              required
              maxLength={100}
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="e.g. Internal HR system"
              className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
            HTTPS destination URL
            <input
              type="url"
              required
              maxLength={2048}
              value={draft.url}
              onChange={(event) => setDraft({ ...draft, url: event.target.value })}
              placeholder="https://hooks.example.com/mindhire"
              className="h-10 rounded-lg border border-gray-200 bg-white px-3 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700 lg:col-span-2">
            Event types
            <textarea
              required
              rows={3}
              value={draft.eventTypes}
              onChange={(event) => setDraft({ ...draft, eventTypes: event.target.value })}
              placeholder="Enter exact event type names, separated by commas or new lines"
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-sr-green focus:ring-2 focus:ring-sr-green/20"
            />
            <span className="font-normal text-gray-500">
              Use the exact event names published by your MindHire workflows. Names are case-sensitive.
            </span>
          </label>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            type="submit"
            disabled={isSaving}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Plus aria-hidden="true" className="h-4 w-4" />}
            {isSaving ? "Saving…" : editingEndpoint ? "Save changes" : "Add endpoint"}
          </button>
        </div>
      </form>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="font-semibold text-gray-900">Configured endpoints</h3>
          <button
            type="button"
            onClick={() => void endpointsQuery.refetch()}
            disabled={endpointsQuery.isFetching}
            aria-label="Refresh webhook endpoints"
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            <RefreshCw aria-hidden="true" className={`h-4 w-4 ${endpointsQuery.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {endpointsQuery.isError ? (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {getErrorMessage(endpointsQuery.error, "Could not load workspace webhooks.")}
            <button type="button" onClick={() => void endpointsQuery.refetch()} className="ml-2 font-semibold underline">Try again</button>
          </div>
        ) : endpointsQuery.isLoading ? (
          <p role="status" className="rounded-lg border border-gray-200 p-4 text-sm text-gray-600">Loading webhook endpoints…</p>
        ) : endpoints.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center">
            <h4 className="font-semibold text-gray-900">No webhook endpoints yet</h4>
            <p className="mt-1 text-sm text-gray-600">Add an endpoint above to configure a workspace integration.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {endpoints.map((endpoint) => (
              <li key={endpoint.id} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="font-semibold text-gray-900">{endpoint.name}</h4>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${endpoint.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-600"}`}>
                        {endpoint.status === "active" ? "Active" : "Disabled"}
                      </span>
                    </div>
                    {endpoint.status === "disabled" && (
                      <p className="mt-1 text-xs text-gray-500">
                        Disabled endpoints cannot be reactivated. Add a new endpoint to resume delivery.
                      </p>
                    )}
                    <p className="mt-1 break-all text-sm text-gray-600">{endpoint.url}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {endpoint.event_types.map((eventType) => (
                        <span key={eventType} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">{eventType}</span>
                      ))}
                    </div>
                    <p className="mt-3 text-xs text-gray-500">Created {formatDate(endpoint.created_at)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 xl:justify-end">
                    <button
                      type="button"
                      onClick={() => startEditing(endpoint)}
                      disabled={isManaging}
                      className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      <Pencil aria-hidden="true" className="h-4 w-4" /> Edit
                    </button>
                    {endpoint.status === "active" && (
                      <>
                        <button
                          type="button"
                          onClick={() => void rotateEndpointSecret(endpoint)}
                          disabled={isManaging || isSaving}
                          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-amber-200 px-3 text-sm font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                        >
                          <RotateCw aria-hidden="true" className="h-4 w-4" /> Rotate secret
                        </button>
                        <button
                          type="button"
                          onClick={() => void disableEndpointNow(endpoint)}
                          disabled={isManaging || isSaving}
                          className="inline-flex h-9 items-center rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          Disable
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => void retireEndpointNow(endpoint)}
                      disabled={isManaging || isSaving}
                      className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      <KeyRound aria-hidden="true" className="h-4 w-4" />
                      Retire endpoint
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {isManaging && <p role="status" className="mt-3 text-sm text-gray-500">Updating webhook configuration…</p>}
    </section>
  );
}
