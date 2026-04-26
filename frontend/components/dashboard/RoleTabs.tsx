"use client";

import type { TabId } from "@/lib/constants";
import { TAB_LABELS, TABS } from "@/lib/constants";

export function RoleTabs({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Dashboard areas">
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
                ? "rounded-md bg-groww-accent px-4 py-2 text-sm font-semibold text-groww-ink"
                : "rounded-md border border-groww-border bg-groww-panel px-4 py-2 text-sm font-medium text-slate-200 hover:border-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent"
            }
            onClick={() => onChange(tab)}
          >
            {TAB_LABELS[tab]}
          </button>
        );
      })}
    </div>
  );
}
