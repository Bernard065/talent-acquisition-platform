"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, ClipboardCheck, Clock3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNotificationActionItems } from "@/lib/api/hooks/notifications";
import type {
  NotificationActionItem,
  NotificationActionItemKind,
} from "@/types/api/notifications";

const dueAtFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});

const subscribeToHydration = () => () => {};
const getClientHydrationSnapshot = () => true;
const getServerHydrationSnapshot = () => false;

function useLocalTimeReady(): boolean {
  return useSyncExternalStore(
    subscribeToHydration,
    getClientHydrationSnapshot,
    getServerHydrationSnapshot,
  );
}

function formatDueAt(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : dueAtFormatter.format(date);
}

function safeNotificationHref(href: string): string {
  return href.startsWith("/") && !href.startsWith("//") && !href.startsWith("/\\")
    ? href
    : "/dashboard";
}

function getPresentation(kind: NotificationActionItemKind) {
  if (kind === "overdue_follow_up") {
    return {
      Icon: Clock3,
      iconClassName: "bg-amber-100 text-amber-800",
      titlePrefix: "Overdue: ",
      datePrefix: "Due",
    };
  }

  return {
    Icon: ClipboardCheck,
    iconClassName: "bg-blue-100 text-blue-800",
    titlePrefix: "",
    datePrefix: "Interview ended",
  };
}

function NotificationRow({
  item,
  onNavigate,
  localTimeReady,
}: {
  item: NotificationActionItem;
  onNavigate: () => void;
  localTimeReady: boolean;
}) {
  const { Icon, iconClassName, titlePrefix, datePrefix } = getPresentation(item.kind);
  const dueAt = localTimeReady ? formatDueAt(item.due_at) : null;

  return (
    <li>
      <Link
        href={safeNotificationHref(item.href)}
        onClick={onNavigate}
        className="flex gap-3 px-4 py-3 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sr-green"
      >
        <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${iconClassName}`}>
          <Icon aria-hidden="true" className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 break-words text-sm font-medium text-gray-900">
            {titlePrefix}{item.title}
          </span>
          <span className="mt-0.5 block break-words text-xs text-gray-700">
            {item.candidate_name} · {item.requisition_title}
          </span>
          {dueAt && (
            <span className="mt-1 block text-xs text-gray-600">
              {datePrefix} {dueAt}
            </span>
          )}
        </span>
      </Link>
    </li>
  );
}

export function NotificationCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const localTimeReady = useLocalTimeReady();
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  const id = useId();
  const panelId = `notification-panel-${id}`;
  const headingId = `notification-heading-${id}`;
  const query = useNotificationActionItems();
  const items = query.data?.items ?? [];
  const attentionLabel = `${items.length} ${items.length === 1 ? "item" : "items"} need attention`;

  useEffect(() => {
    const closePanel = window.setTimeout(() => setIsOpen(false), 0);
    return () => window.clearTimeout(closePanel);
  }, [pathname]);

  useEffect(() => {
    if (!isOpen) return;

    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleFocusIn(event: FocusEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      const focusWasInPanel = Boolean(panelRef.current?.contains(document.activeElement));
      setIsOpen(false);
      if (focusWasInPanel) triggerRef.current?.focus();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("focusin", handleFocusIn);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("focusin", handleFocusIn);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      <Button
        ref={triggerRef}
        type="button"
        variant="ghost"
        size="icon"
        className="relative size-10 rounded-full text-gray-600 hover:text-sr-text-blue"
        aria-label={items.length ? `Notifications, ${attentionLabel}` : "Notifications"}
        aria-expanded={isOpen}
        aria-controls={isOpen ? panelId : undefined}
        onClick={() => setIsOpen((open) => !open)}
      >
        <Bell aria-hidden="true" className="size-5" />
        {items.length > 0 && (
          <span aria-hidden="true" className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-red-700 px-1 text-center text-[11px] font-bold leading-4 text-white">
            {items.length > 99 ? "99+" : items.length}
          </span>
        )}
      </Button>

      {isOpen && (
        <section
          ref={panelRef}
          id={panelId}
          aria-labelledby={headingId}
          className="fixed inset-x-4 top-[4.25rem] z-50 max-h-[calc(100dvh-5rem)] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:max-h-none sm:w-[min(24rem,calc(100vw-2rem))]"
        >
          <header className="border-b border-gray-100 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 id={headingId} className="text-sm font-semibold text-sr-text-blue">Notifications</h2>
              {items.length > 0 && (
                <span className="text-xs text-gray-600">{attentionLabel}</span>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-600">Overdue follow-ups and feedback still to submit.</p>
          </header>

          {query.isLoading && !query.data ? (
            <p className="px-4 py-6 text-sm text-gray-600" role="status">Loading notifications…</p>
          ) : query.isError && !query.data ? (
            <div className="px-4 py-5">
              <p className="text-sm text-red-800" role="alert">Notifications couldn’t be loaded.</p>
              <Button
                className="mt-3"
                variant="outline"
                size="sm"
                disabled={query.isFetching}
                onClick={() => void query.refetch()}
              >
                {query.isFetching ? "Retrying…" : "Try again"}
              </Button>
            </div>
          ) : (
            <>
              {query.isError && (
                <p className="mx-4 mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
                  Couldn’t refresh notifications. Showing the last loaded results.
                </p>
              )}
              {items.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-gray-700" role="status">You’re all caught up.</p>
              ) : (
                <ul className="max-h-[min(28rem,calc(100dvh-8rem))] divide-y divide-gray-100 overflow-y-auto">
                  {items.map((item) => (
                    <NotificationRow
                      key={item.id}
                      item={item}
                      localTimeReady={localTimeReady}
                      onNavigate={() => setIsOpen(false)}
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
