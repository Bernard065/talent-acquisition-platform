"use client";

import { useEffect, useRef, useState } from "react";
import { CalendarDays, Check, ExternalLink, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api/errors";
import {
  useBeginCalendarAuthorization,
  useCalendarConnections,
} from "@/lib/api/hooks/calendar-connections";

export function IntegrationsTab() {
  const connectionsQuery = useCalendarConnections();
  const authorizationMutation = useBeginCalendarAuthorization();
  const [isConnecting, setIsConnecting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const googleConnection = connectionsQuery.data?.find(
    (connection) => connection.provider === "google",
  );
  const isConnected = googleConnection?.status === "active";

  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, []);

  async function connectGoogleCalendar() {
    if (isConnecting) return;

    const popup = window.open(
      "about:blank",
      "google-calendar-authorization",
      "popup,width=560,height=720",
    );

    if (!popup) {
      setConnectionError("Allow pop-ups for this site to connect Google Calendar.");
      return;
    }
    popup.opener = null;

    setIsConnecting(true);
    setStatusMessage(null);
    setConnectionError(null);

    try {
      const authorization = await authorizationMutation.mutateAsync("google");
      const authorizationDeadline = Date.now() + authorization.expires_in_seconds * 1000;
      popup.location.assign(authorization.authorization_url);
      setStatusMessage("Complete authorization in the Google window. This page will update when it finishes.");

      const refreshUntilConnected = async () => {
        if (Date.now() >= authorizationDeadline) {
          popup.close();
          setIsConnecting(false);
          setConnectionError("Google authorization expired. Start the connection again.");
          return;
        }

        if (popup.closed) {
          await connectionsQuery.refetch();
          setIsConnecting(false);
          return;
        }

        const result = await connectionsQuery.refetch();
        const connected = result.data?.some(
          (connection) => connection.provider === "google" && connection.status === "active",
        );

        if (connected) {
          popup.close();
          setIsConnecting(false);
          setStatusMessage("Google Calendar is connected.");
          return;
        }

        pollTimer.current = setTimeout(() => void refreshUntilConnected(), 1500);
      };

      pollTimer.current = setTimeout(() => void refreshUntilConnected(), 1500);
    } catch (error) {
      popup.close();
      setIsConnecting(false);
      setConnectionError(
        error instanceof ApiError
          ? error.detail
          : "Could not start Google Calendar authorization. Try again.",
      );
    }
  }

  return (
    <section className="max-w-3xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-gray-100 bg-gray-50 text-sr-text-blue">
            <CalendarDays aria-hidden="true" className="h-6 w-6" />
          </div>
          <div>
            <h2 className="font-bold text-gray-900">Google Calendar</h2>
            <p className="mt-1 text-sm text-gray-500">Scheduling</p>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-gray-600">
              Connect your calendar so interview events involving you can be synchronized.
              This connection is private to your account.
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 self-start rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-600 sm:self-auto">
          {connectionsQuery.isLoading ? (
            <><RefreshCw aria-hidden="true" className="h-3.5 w-3.5 animate-spin" /> Checking</>
          ) : isConnected ? (
            <><Check aria-hidden="true" className="h-3.5 w-3.5 text-emerald-600" /> Connected</>
          ) : googleConnection?.status === "disabled" ? (
            "Disconnected"
          ) : (
            "Not connected"
          )}
        </div>
      </div>

      <div className="mt-6 border-t border-gray-100 pt-5">
        {connectionsQuery.isError ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p role="alert" className="text-sm text-red-700">Could not load your calendar connection.</p>
            <button
              type="button"
              onClick={() => void connectionsQuery.refetch()}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-gray-200 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <RefreshCw aria-hidden="true" className="h-4 w-4" /> Retry
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => void connectGoogleCalendar()}
            disabled={isConnected || isConnecting || connectionsQuery.isLoading}
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-sr-mint px-4 text-sm font-semibold text-sr-text-blue transition-colors hover:bg-sr-green hover:text-white disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            {isConnecting ? "Waiting for authorization…" : isConnected ? "Google Calendar connected" : "Connect Google Calendar"}
            {!isConnected && !isConnecting && <ExternalLink aria-hidden="true" className="h-4 w-4" />}
          </button>
        )}

        {statusMessage && <p role="status" className="mt-3 text-sm text-emerald-700">{statusMessage}</p>}
        {connectionError && <p role="alert" className="mt-3 text-sm text-red-700">{connectionError}</p>}
        <p className="mt-4 text-xs text-gray-500">
          Other integrations will appear here when their connection flows are available.
        </p>
      </div>
    </section>
  );
}
