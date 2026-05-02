"use client";

import type { TabId } from "@/lib/constants";
import { TAB_LABELS, TABS } from "@/lib/constants";

const TAB_COPY: Record<TabId, string> = {
  customer: "AI assistant",
  product: "Weekly Pulse",
  advisor: "Approvals",
};

export function RoleTabs({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
}) {
  return (
    <div
      className="grid gap-1 rounded-2xl border border-groww-border bg-groww-surfaceSoft p-1"
      role="tablist"
      aria-label="Dashboard areas"
    >
      {TABS.map((tab) => {
        const selected = tab === active;
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className={
              selected
                ? "focus-ring rounded-xl bg-white px-4 py-3 text-left text-sm font-semibold text-groww-text shadow-sm"
                : "focus-ring rounded-xl px-4 py-3 text-left text-sm font-semibold text-groww-muted transition hover:bg-white/70 hover:text-groww-text"
            }
            onClick={() => onChange(tab)}
          >
            <span className="block">{TAB_LABELS[tab]}</span>
            <span className="mt-0.5 block text-xs font-medium text-groww-faint">{TAB_COPY[tab]}</span>
          </button>
        );
      })}
    </div>
  );
}
