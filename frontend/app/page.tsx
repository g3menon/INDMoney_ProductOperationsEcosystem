"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AdvisorTab } from "@/components/advisor/AdvisorTab";
import { CustomerTab } from "@/components/customer/CustomerTab";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { ProductTab } from "@/components/product/ProductTab";
import { ErrorState } from "@/components/shared/ErrorState";
import { InlineStatus } from "@/components/shared/InlineStatus";
import { LoadingState } from "@/components/shared/LoadingState";
import type { ApiEnvelope } from "@/lib/api-client";
import { fetchJson } from "@/lib/api-client";
import { BADGE_GROUPS } from "@/lib/badge-config";
import type { TabId } from "@/lib/constants";

type HealthData = {
  status: string;
  correlation_id: string;
  supabase: { reachable: boolean; detail: string };
  settings: Record<string, unknown>;
};

type BadgePayload = {
  customer: Record<string, number | boolean>;
  product: Record<string, number | boolean | string | null>;
  advisor: Record<string, number | boolean>;
  supabase_connected: boolean;
};

export default function Page() {
  const [tab, setTab] = useState<TabId>("customer");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<ApiEnvelope<HealthData> | null>(null);
  const [badges, setBadges] = useState<ApiEnvelope<BadgePayload> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, b] = await Promise.all([
        fetchJson<HealthData>("/api/v1/health"),
        fetchJson<BadgePayload>("/api/v1/dashboard/badges"),
      ]);
      setHealth(h);
      setBadges(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setHealth(null);
      setBadges(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const partial = useMemo(() => {
    if (!health || !badges) return false;
    return health.success !== true || badges.success !== true;
  }, [health, badges]);

  const badgeStrip = useMemo(() => {
    if (loading) return <LoadingState label="Loading backend status…" />;
    if (error) {
      return <ErrorState title="Backend unreachable" message={error} onRetry={() => void load()} />;
    }
    if (!health || !badges) {
      return <ErrorState title="Unexpected response" message="Missing health or badge payload." onRetry={() => void load()} />;
    }

    const healthTone =
      health.data?.status === "ok" ? "success" : health.data?.status === "degraded" ? "warning" : "neutral";
    const supa = Boolean(badges.data?.supabase_connected);
    return (
      <div className="flex flex-col items-start gap-2 md:items-end">
        <InlineStatus
          tone={healthTone}
          label={`API ${health.data?.status ?? "unknown"} · correlation ${health.data?.correlation_id ?? "—"}`}
        />
        <InlineStatus tone={supa ? "success" : "warning"} label={`Supabase reachability: ${supa ? "OK" : "Check keys"}`} />
        {partial ? (
          <InlineStatus tone="warning" label="Partial: one of the envelope checks reported unsuccessful." />
        ) : null}
      </div>
    );
  }, [badges, error, health, loading, partial, load]);

  const tabBadges = badges?.data?.[tab];

  return (
    <DashboardShell activeTab={tab} onTabChange={setTab} badgeStrip={badgeStrip}>
      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {tab === "customer" ? <CustomerTab /> : null}
          {tab === "product" ? <ProductTab /> : null}
          {tab === "advisor" ? <AdvisorTab /> : null}
        </div>
        <aside className="space-y-4">
          <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
            <h2 className="text-sm font-semibold text-white">Badge preview · {tab}</h2>
            <p className="mt-1 text-xs text-slate-400">Counts are backend-owned (`GET /api/v1/dashboard/badges`).</p>
            <dl className="mt-4 space-y-3 text-sm">
              {BADGE_GROUPS[tab].map((row) => {
                const raw = tabBadges ? (tabBadges as Record<string, unknown>)[row.key] : undefined;
                const value =
                  typeof raw === "boolean" ? (raw ? "Yes" : "No") : raw === null || raw === undefined ? "—" : String(raw);
                return (
                  <div key={row.key} className="flex flex-col rounded-md border border-groww-border/60 bg-groww-ink/40 p-3">
                    <dt className="text-xs font-semibold text-slate-200">{row.label}</dt>
                    <dd className="mt-1 text-lg font-semibold text-white">{value}</dd>
                    <p className="mt-1 text-[11px] text-slate-500">{row.description}</p>
                  </div>
                );
              })}
            </dl>
          </div>
        </aside>
      </section>
    </DashboardShell>
  );
}
