import type { ReactNode } from "react";

import type { TabId } from "@/lib/constants";
import { DEFAULT_TZ_LABEL } from "@/lib/formatters";
import { RoleTabs } from "./RoleTabs";

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
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-4 border-b border-groww-border pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">Groww · Product Operations</p>
          <h1 className="mt-1 text-2xl font-semibold text-white">Operations dashboard</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            Phase 1 shell: Customer, Product, and Advisor surfaces share one backend source of truth. Times are shown
            with explicit timezone context: <span className="text-slate-200">{DEFAULT_TZ_LABEL}</span>.
          </p>
        </div>
        {badgeStrip ? <div className="md:text-right">{badgeStrip}</div> : null}
      </header>

      <RoleTabs active={activeTab} onChange={onTabChange} />

      <main className="flex-1">{children}</main>
    </div>
  );
}
