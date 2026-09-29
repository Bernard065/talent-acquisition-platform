import Link from "next/link";
import type { ReactNode } from "react";

type NavigationItem = {
  label: string;
  marker: string;
  active?: boolean;
};

const workspaceItems: NavigationItem[] = [
  { label: "Overview", marker: "01", active: true },
  { label: "Requisitions", marker: "02" },
  { label: "Candidates", marker: "03" },
  { label: "Applications", marker: "04" },
  { label: "Interviews", marker: "05" },
  { label: "Offers & onboarding", marker: "06" },
];

const managementItems: NavigationItem[] = [
  { label: "Reports", marker: "07" },
  { label: "Settings", marker: "08" },
];

function NavigationGroup({
  label,
  items,
}: {
  label: string;
  items: NavigationItem[];
}) {
  return (
    <div
      className={`grid content-start max-[760px]:flex-none ${label === "Manage" ? "max-[760px]:ml-1.5 max-[760px]:border-l max-[760px]:border-line max-[760px]:pl-1.5" : ""}`}
    >
      <p className="m-0 px-2.75 pb-2.25 text-2.5 font-bold tracking-[1.3px] text-muted uppercase max-[760px]:sr-only">
        {label}
      </p>
      <ul className="m-0 grid list-none gap-0.75 p-0 max-[760px]:flex max-[760px]:w-max max-[760px]:gap-1.25">
        {items.map((item) => (
          <li key={item.label}>
            {item.active ? (
              <Link
                aria-current="page"
                className="flex min-h-9.75 w-full items-center gap-2.75 rounded-[7px] bg-accent-pale px-2.75 text-left text-3 font-bold text-accent-dark no-underline max-[760px]:min-h-8.5 max-[760px]:w-auto max-[760px]:whitespace-nowrap max-[760px]:px-2.5"
                href="/"
              >
                <span
                  aria-hidden="true"
                  className="w-4.75 shrink-0 font-display text-2.25 font-bold text-accent max-[760px]:hidden"
                >
                  {item.marker}
                </span>
                <span>{item.label}</span>
              </Link>
            ) : (
              <button
                aria-disabled="true"
                className="flex min-h-9.75 w-full cursor-not-allowed items-center gap-2.75 rounded-[7px] border-0 bg-transparent px-2.75 text-left text-3 text-disabled opacity-72 max-[760px]:min-h-8.5 max-[760px]:w-auto max-[760px]:whitespace-nowrap max-[760px]:px-2.5"
                disabled
                title="This area will be added in a later frontend step."
                type="button"
              >
                <span
                  aria-hidden="true"
                  className="w-4.75 shrink-0 font-display text-2.25 font-bold text-disabled-marker max-[760px]:hidden"
                >
                  {item.marker}
                </span>
                <span>{item.label}</span>
                <span className="ml-auto text-2.25 text-disabled-label max-[760px]:ml-px">
                  Soon
                </span>
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-[252px_minmax(0,1fr)] max-[1050px]:grid-cols-[220px_minmax(0,1fr)] max-[760px]:block">
      <a
        className="fixed -top-20 left-3 z-50 rounded-lg bg-accent-dark px-3.5 py-2.5 text-white no-underline focus:top-3"
        href="#main-content"
      >
        Skip to content
      </a>

      <aside
        aria-label="Application sidebar"
        className="sticky top-0 flex h-screen min-h-150 flex-col border-r border-line bg-white px-4.25 pt-6.75 pb-4.5 max-[760px]:static max-[760px]:h-auto max-[760px]:min-h-0 max-[760px]:border-r-0 max-[760px]:border-b max-[760px]:px-4.5 max-[760px]:pt-3.25 max-[760px]:pb-2.5"
      >
        <Link
          aria-label="Talent Acquisition home"
          className="flex items-center gap-2.75 px-2.25 pb-7.25 text-ink no-underline max-[760px]:px-0.5 max-[760px]:pb-3.25"
          href="/"
        >
          <span
            aria-hidden="true"
            className="grid size-9.25 shrink-0 place-items-center rounded-[10px] bg-accent-dark font-display text-4.25 font-extrabold text-logo-mark"
          >
            T
          </span>
          <span className="grid gap-px text-3.25 leading-[1.2]">
            <strong className="font-display text-4 tracking-[-0.6px]">
              talent
            </strong>
            <span className="text-2.5 tracking-[0.08px] text-muted">
              acquisition platform
            </span>
          </span>
        </Link>

        <nav
          aria-label="Main navigation"
          className="grid content-start gap-6.5 max-[760px]:-mx-4.5 max-[760px]:flex max-[760px]:gap-0 max-[760px]:overflow-x-auto max-[760px]:px-4.5 max-[760px]:pb-1.25"
        >
          <NavigationGroup label="Workspace" items={workspaceItems} />
          <NavigationGroup label="Manage" items={managementItems} />
        </nav>

        <div className="mt-auto flex items-center gap-2.25 border-t border-line px-2.75 pt-4 pb-1 text-2.5 text-muted max-[760px]:hidden">
          <span
            aria-hidden="true"
            className="size-1.75 shrink-0 rounded-full bg-status-warning"
          />
          <span>Frontend foundation</span>
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="flex min-h-17 items-center justify-between gap-5 border-b border-line bg-white/80 px-[clamp(22px,4.5vw,68px)] max-[760px]:min-h-13.75 max-[760px]:px-5">
          <nav
            aria-label="Breadcrumb"
            className="flex items-center gap-2.25 text-2.75 text-muted"
          >
            <span>Workspace</span>
            <span aria-hidden="true" className="text-breadcrumb-muted">
              /
            </span>
            <span className="font-semibold text-ink-soft">Overview</span>
          </nav>
          <div className="flex items-center gap-5.5 max-[760px]:gap-0">
            <span className="inline-flex items-center gap-1.75 text-2.5 font-semibold text-status-warning-label">
              <span
                aria-hidden="true"
                className="size-1.75 shrink-0 rounded-full bg-status-warning"
              />
              API not connected
            </span>
            <button
              className="inline-flex items-center gap-2.25 border-0 bg-transparent p-0 text-2.5 text-control-muted"
              disabled
              title="Authentication will be connected in a later frontend step."
              type="button"
            >
              <span
                aria-hidden="true"
                className="grid size-7.25 place-items-center rounded-full border border-control-line bg-surface-soft text-icon-muted"
              >
                —
              </span>
              <span className="max-[760px]:sr-only">
                Sign-in not configured
              </span>
            </button>
          </div>
        </header>

        <main
          className="w-full max-w-305 flex-1 self-center px-[clamp(22px,4.5vw,68px)] pt-12.75 pb-9 max-[760px]:px-5 max-[760px]:pt-7.5 max-[760px]:pb-7.5"
          id="main-content"
        >
          {children}
        </main>

        <footer className="flex justify-between gap-5 border-t border-line px-[clamp(22px,4.5vw,68px)] pt-3.75 pb-4.75 text-2.25 text-footer-muted max-[760px]:flex-col max-[760px]:gap-1.25 max-[760px]:px-5">
          <span>Talent Acquisition Platform</span>
          <span>Development preview · No recruiting data loaded</span>
        </footer>
      </div>
    </div>
  );
}
