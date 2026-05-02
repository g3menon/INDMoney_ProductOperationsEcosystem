import type { ReactNode } from "react";

import type { TabId } from "@/lib/constants";
import { DEFAULT_TZ_LABEL } from "@/lib/formatters";
import { RoleTabs } from "./RoleTabs";

const ROLE_HEADLINES: Record<TabId, { eyebrow: string; title: string; description: string }> = {
  customer: {
    eyebrow: "Customer surface",
    title: "Customer AI assistant",
    description: "Answer fund questions, explain fees, and help customers move into advisor booking when needed.",
  },
  product: {
    eyebrow: "Product surface",
    title: "Weekly Pulse",
    description: "Monitor themes, quotes, actions, and booking demand signals from customer feedback.",
  },
  advisor: {
    eyebrow: "Advisor surface",
    title: "Advisor Console",
    description: "Review booking requests, approve customer confirmations, and prepare for upcoming calls.",
  },
};

export function DashboardShell({
  activeTab,
  onTabChange,
  badgeStrip,
  children,
}: {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  badgeStrip?: ReactNode;
  children: ReactNode;
}) {
  const headline = ROLE_HEADLINES[activeTab];

  return (
    <div className="min-h-screen px-4 py-4 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-5 lg:flex-row">
        <aside className="soft-panel top-4 flex shrink-0 flex-col gap-6 p-4 lg:sticky lg:h-[calc(100vh-2rem)] lg:w-[264px]">
          <div className="rounded-2xl bg-gradient-to-br from-groww-accent to-groww-accentBlue p-4 text-white shadow-card">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/20 text-lg font-bold">G</div>
            <h1 className="mt-4 text-xl font-semibold">Groww Ops AI</h1>
            <p className="mt-1 text-sm text-white/80">Product Operations Dashboard</p>
          </div>

          <div>
            <p className="mb-2 px-2 text-[11px] font-bold uppercase tracking-[0.16em] text-groww-faint">Surfaces</p>
            <RoleTabs active={activeTab} onChange={onTabChange} />
          </div>

          <div className="mt-auto rounded-2xl border border-groww-border bg-groww-surfaceSoft p-4">
            <p className="text-xs font-semibold text-groww-faint">Timezone</p>
            <p className="mt-1 text-sm font-semibold text-groww-text">{DEFAULT_TZ_LABEL}</p>
            <p className="mt-2 text-xs leading-5 text-groww-muted">Booking slots and pulse cadence are shown in IST.</p>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="soft-panel mb-5 flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-groww-accent">{headline.eyebrow}</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight text-groww-text">{headline.title}</h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-groww-muted">{headline.description}</p>
            </div>
            {badgeStrip ? <div className="flex flex-wrap gap-2 md:justify-end">{badgeStrip}</div> : null}
          </header>

          <main className="min-w-0 pb-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
