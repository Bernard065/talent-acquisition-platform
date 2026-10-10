"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type TurnstileRenderOptions = {
  sitekey: string;
  action: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
};

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: TurnstileRenderOptions) => string;
      reset: (widgetId?: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

export function TurnstileChallenge({
  onToken,
  onError,
  resetSignal,
}: {
  onToken: (token: string | null) => void;
  onError: (message: string) => void;
  resetSignal: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [scriptReady, setScriptReady] = useState(false);

  useEffect(() => {
    if (!siteKey || !scriptReady || !containerRef.current || !window.turnstile) {
      return;
    }

    const widgetId = window.turnstile.render(containerRef.current, {
      sitekey: siteKey,
      action: "public_application",
      callback: (token) => onToken(token),
      "expired-callback": () => onToken(null),
      "error-callback": () => {
        onToken(null);
        onError("The security check could not be verified. Please try again.");
      },
    });
    widgetIdRef.current = widgetId;

    return () => {
      if (widgetIdRef.current) {
        window.turnstile?.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [onError, onToken, scriptReady]);

  useEffect(() => {
    if (resetSignal > 0 && widgetIdRef.current) {
      window.turnstile?.reset(widgetIdRef.current);
      onToken(null);
    }
  }, [onToken, resetSignal]);

  if (!siteKey) return null;

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-gray-700">Security check</p>
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onReady={() => setScriptReady(true)}
        onError={() => onError("The security check could not be loaded. Please refresh and try again.")}
      />
      <div ref={containerRef} aria-label="Cloudflare security check" />
    </div>
  );
}
