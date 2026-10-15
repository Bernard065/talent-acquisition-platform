"use client";

import { useState, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import {
  useCreateHrisConnection,
  useDeleteHrisConnection,
  useDisableHrisConnection,
  useHrisConnections,
  useHrisHandoffs,
  useRetryHrisHandoff,
} from "@/lib/api/hooks/hris";
import type { HrisHandoffStatus } from "@/types/api/hris";

const handoffLabels: Record<HrisHandoffStatus, string> = {
  pending: "Waiting to sync",
  processing: "Sending",
  succeeded: "Sent",
  retryable_failed: "Retry scheduled",
  failed: "Needs attention",
};

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not attempted";
}

export function HrisIntegrationSection() {
  const { data: session } = useSession();
  const isAdmin = session?.roles?.includes("tenant_admin") ?? false;
  const connections = useHrisConnections(isAdmin);
  const create = useCreateHrisConnection();
  const disable = useDisableHrisConnection();
  const remove = useDeleteHrisConnection();
  const retry = useRetryHrisHandoff();
  const [name, setName] = useState("BambooHR");
  const [companyDomain, setCompanyDomain] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [filter, setFilter] = useState<HrisHandoffStatus | "">("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const filteredHandoffs = useHrisHandoffs(filter || undefined, cursor, isAdmin);
  const activeConnection = connections.data?.items.find((connection) => connection.status === "active");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    create.mutate({
      request: {
        name: name.trim(),
        provider: "bamboohr",
        credentials: {
          api_key: apiKey,
          company_domain: companyDomain.trim().toLowerCase(),
        },
      },
      idempotencyKey: crypto.randomUUID(),
    }, {
      onSuccess: () => {
        setApiKey("");
        setMessage("BambooHR is connected. New onboarding starts will be handed off automatically.");
      },
      onError: () => setError("We couldn’t save this HRIS connection. Check the company domain and credentials, then try again."),
    });
  }

  if (!isAdmin) return null;

  return (
    <section className="mt-6 max-w-4xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h2 className="text-lg font-semibold text-sr-text-blue">HRIS handoff</h2>
        <p className="mt-1 text-sm leading-relaxed text-gray-600">Configure the supported BambooHR connection and monitor employee handoffs queued from onboarding.</p>
      </div>

      <div className="mt-5 rounded-lg border border-gray-100 p-4">
        <h3 className="font-medium text-gray-900">BambooHR connection</h3>
        {connections.isLoading ? <p className="mt-3 text-sm text-gray-600">Loading connection…</p> : connections.isError ? (
          <p role="alert" className="mt-3 text-sm text-red-800">We couldn’t load HRIS connection settings.</p>
        ) : activeConnection ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-gray-900">{activeConnection.name}</p>
              <p className="mt-1 text-xs text-gray-600">BambooHR · Active · Updated {formatDate(activeConnection.updated_at)}</p>
            </div>
            <button type="button" disabled={disable.isPending} onClick={() => {
              if (!window.confirm("Disable BambooHR handoffs for future onboarding plans?")) return;
              disable.mutate({ id: activeConnection.id, version: activeConnection.version, idempotencyKey: crypto.randomUUID() }, {
                onSuccess: () => setMessage("BambooHR has been disabled for new handoffs."),
                onError: () => setError("The connection could not be disabled. Refresh and try again."),
              });
            }} className="h-9 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50">Disable</button>
          </div>
        ) : (
          <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
            <label>
              <span className="mb-1 block text-sm font-medium text-gray-700">Connection name</span>
              <input required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
            </label>
            <label>
              <span className="mb-1 block text-sm font-medium text-gray-700">BambooHR company domain</span>
              <div className="flex h-10 overflow-hidden rounded-lg border border-gray-200">
                <input required pattern="[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]|[a-zA-Z0-9]" value={companyDomain} onChange={(event) => setCompanyDomain(event.target.value)} className="min-w-0 flex-1 px-3 text-sm outline-none" placeholder="your-company" />
                <span className="flex items-center bg-gray-50 px-2 text-xs text-gray-500">.bamboohr.com</span>
              </div>
            </label>
            <label className="sm:col-span-2">
              <span className="mb-1 block text-sm font-medium text-gray-700">BambooHR API key</span>
              <input required type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm" />
            </label>
            <p className="text-xs leading-relaxed text-gray-500 sm:col-span-2">Credentials are stored in the configured secret vault. The platform supports one active HRIS destination per workspace.</p>
            {error && <p role="alert" className="text-sm text-red-800 sm:col-span-2">{error}</p>}
            <button type="submit" disabled={create.isPending} className="h-10 justify-self-start rounded-lg bg-sr-text-blue px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">{create.isPending ? "Connecting…" : "Connect BambooHR"}</button>
          </form>
        )}
        {connections.data?.items.filter((item) => item.status === "disabled").map((connection) => (
          <div key={connection.id} className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md bg-gray-50 p-3">
            <p className="text-sm text-gray-700">{connection.name} · Disabled</p>
            <button type="button" disabled={remove.isPending} onClick={() => {
              if (!window.confirm("Remove this disabled connection? Existing handoff history will be retained.")) return;
              remove.mutate({ id: connection.id, version: connection.version, idempotencyKey: crypto.randomUUID() }, {
                onSuccess: () => setMessage("Disabled connection removed."),
                onError: () => setError("The disabled connection could not be removed."),
              });
            }} className="text-sm font-medium text-red-700 underline disabled:opacity-50">Remove</button>
          </div>
        ))}
      </div>

      <div className="mt-7 border-t border-gray-100 pt-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="font-medium text-gray-900">Recent handoffs</h3>
            <p className="mt-1 text-xs text-gray-500">Refreshes automatically every 15 seconds. Credentials and candidate details are not shown here.</p>
          </div>
          <label className="text-sm">
            <span className="sr-only">Filter handoff status</span>
            <select value={filter} onChange={(event) => { setFilter(event.target.value as HrisHandoffStatus | ""); setCursor(undefined); }} className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 sm:w-auto">
              <option value="">All statuses</option>
              {Object.entries(handoffLabels).map(([status, label]) => <option key={status} value={status}>{label}</option>)}
            </select>
          </label>
        </div>
        {filteredHandoffs.isLoading ? <p className="mt-4 text-sm text-gray-600" role="status">Loading handoffs…</p> : filteredHandoffs.isError ? (
          <p role="alert" className="mt-4 text-sm text-red-800">We couldn’t load HRIS handoff status.</p>
        ) : !filteredHandoffs.data?.items.length ? (
          <p className="mt-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">No HRIS handoffs yet. Starting onboarding for a hired candidate will queue a handoff when a connection is active.</p>
        ) : (
          <>
            <ul className="mt-4 divide-y divide-gray-100 rounded-lg border border-gray-100">
              {filteredHandoffs.data.items.map((handoff) => (
                <li key={handoff.id} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900">BambooHR handoff</p>
                    <p className="mt-1 text-xs text-gray-500">Updated {formatDate(handoff.updated_at)} · {handoff.attempt_count} attempts</p>
                    {handoff.last_error_code && <p className="mt-1 break-all text-xs text-red-700">Issue: {handoff.last_error_code}</p>}
                  </div>
                  <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${handoff.status === "succeeded" ? "bg-emerald-50 text-emerald-800" : handoff.status === "failed" || handoff.status === "retryable_failed" ? "bg-amber-50 text-amber-900" : "bg-blue-50 text-blue-800"}`}>{handoffLabels[handoff.status]}</span>
                  {handoff.status === "failed" && (
                    <button
                      type="button"
                      disabled={retry.isPending}
                      onClick={() => retry.mutate({
                        id: handoff.id,
                        version: handoff.version,
                        idempotencyKey: crypto.randomUUID(),
                      }, {
                        onSuccess: () => setMessage("The HRIS handoff retry has been queued."),
                        onError: () => setError("The handoff could not be retried. Refresh the status and try again."),
                      })}
                      className="h-9 w-fit rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {retry.isPending ? "Queueing…" : "Retry handoff"}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {filteredHandoffs.data.next_cursor && (
              <button type="button" onClick={() => setCursor(filteredHandoffs.data?.next_cursor ?? undefined)} className="mt-3 text-sm font-medium text-sr-text-blue underline">Load older handoffs</button>
            )}
          </>
        )}
      </div>
      {message && <p role="status" className="mt-4 text-sm text-emerald-800">{message}</p>}
      {error && !connections.isError && <p role="alert" className="mt-4 text-sm text-red-800">{error}</p>}
    </section>
  );
}
