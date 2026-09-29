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
    <div className="navigation-group">
      <p className="navigation-group-label">{label}</p>
      <ul className="navigation-list">
        {items.map((item) => (
          <li key={item.label}>
            {item.active ? (
              <Link
                aria-current="page"
                className="navigation-link is-active"
                href="/"
              >
                <span aria-hidden="true" className="navigation-marker">
                  {item.marker}
                </span>
                <span>{item.label}</span>
              </Link>
            ) : (
              <button
                aria-disabled="true"
                className="navigation-link is-pending"
                disabled
                title="This area will be added in a later frontend step."
                type="button"
              >
                <span aria-hidden="true" className="navigation-marker">
                  {item.marker}
                </span>
                <span>{item.label}</span>
                <span className="navigation-soon">Soon</span>
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
    <div className="app-frame">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <aside aria-label="Application sidebar" className="sidebar">
        <Link aria-label="Talent Acquisition home" className="brand" href="/">
          <span aria-hidden="true" className="brand-mark">
            T
          </span>
          <span className="brand-name">
            <strong>talent</strong>
            <span>acquisition platform</span>
          </span>
        </Link>

        <nav aria-label="Main navigation" className="sidebar-navigation">
          <NavigationGroup label="Workspace" items={workspaceItems} />
          <NavigationGroup label="Manage" items={managementItems} />
        </nav>

        <div className="sidebar-footer">
          <span aria-hidden="true" className="environment-dot" />
          <span>Frontend foundation</span>
        </div>
      </aside>

      <div className="app-content">
        <header className="topbar">
          <nav aria-label="Breadcrumb" className="breadcrumb">
            <span>Workspace</span>
            <span aria-hidden="true" className="breadcrumb-separator">
              /
            </span>
            <span className="breadcrumb-current">Overview</span>
          </nav>
          <div className="topbar-actions">
            <span className="connection-status">
              <span aria-hidden="true" className="status-indicator" />
              API not connected
            </span>
            <button
              className="account-button"
              disabled
              title="Authentication will be connected in a later frontend step."
              type="button"
            >
              <span aria-hidden="true" className="account-avatar">
                —
              </span>
              <span>Sign-in not configured</span>
            </button>
          </div>
        </header>

        <main className="main-content" id="main-content">
          {children}
        </main>

        <footer className="page-footer">
          <span>Talent Acquisition Platform</span>
          <span>Development preview · No recruiting data loaded</span>
        </footer>
      </div>
    </div>
  );
}
