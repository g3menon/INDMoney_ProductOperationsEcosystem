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
      setError(e instanceof Error ? e.message : "We could not refresh service status.");
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
    if (loading) return <LoadingState label="Checking services" />;
    if (error) {
      return <ErrorState title="Service check needs attention" message={error} onRetry={() => void load()} />;
    }
    if (!health || !badges) {
      return (
        <ErrorState
          title="Status unavailable"
          message="We could not refresh the dashboard status."
          onRetry={() => void load()}
        />
      );
    }

    const healthTone =
      health.data?.status === "ok" ? "success" : health.data?.status === "degraded" ? "warning" : "neutral";
    const supabaseConnected = Boolean(badges.data?.supabase_connected);
    return (
      <>
        <InlineStatus
          tone={healthTone}
          label={health.data?.status === "ok" ? "Services healthy" : `Services ${health.data?.status ?? "checking"}`}
        />
        <InlineStatus tone={supabaseConnected ? "success" : "warning"} label={supabaseConnected ? "Data connected" : "Data connection pending"} />
        {partial ? <InlineStatus tone="warning" label="Some data may be delayed" /> : null}
      </>
    );
  }, [badges, error, health, loading, partial, load]);

  return (
    <DashboardShell activeTab={tab} onTabChange={setTab} badgeStrip={badgeStrip}>
      {tab === "customer" ? <CustomerTab /> : null}
      {tab === "product" ? <ProductTab /> : null}
      {tab === "advisor" ? <AdvisorTab /> : null}
    </DashboardShell>
  );
}
