"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/shared/ErrorState";
import { InlineStatus } from "@/components/shared/InlineStatus";
import { LoadingState } from "@/components/shared/LoadingState";
import type { ApiEnvelope } from "@/lib/api-client";
import { fetchJson } from "@/lib/api-client";
import { formatShortIso } from "@/lib/formatters";

type WeeklyPulse = {
  pulse_id: string;
  created_at: string;
  metrics: { reviews_considered: number; average_rating: number; lookback_weeks: number };
  themes: { theme: string; summary: string; count: number }[];
  quotes: { review_id: string; quote: string; rating: number }[];
  recommended_actions: string[];
  narrative: string;
  degraded: boolean;
  degraded_reason?: string | null;
};

export function ProductTab() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<ApiEnvelope<WeeklyPulse | null> | null>(null);
  const [history, setHistory] = useState<ApiEnvelope<WeeklyPulse[]> | null>(null);
  const [email, setEmail] = useState("");
  const [actionBusy, setActionBusy] = useState<"none" | "subscribe" | "unsubscribe" | "generate">("none");
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setActionMsg(null);
    try {
      const [c, h] = await Promise.all([
        fetchJson<WeeklyPulse | null>("/api/v1/pulse/current"),
        fetchJson<WeeklyPulse[]>("/api/v1/pulse/history?limit=10"),
      ]);
      setCurrent(c);
      setHistory(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setCurrent(null);
      setHistory(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const idealCurrent = current?.data ?? null;
  const historyRows = history?.data ?? [];

  const generateFixture = useCallback(async () => {
    setActionBusy("generate");
    setActionMsg(null);
    try {
      await fetchJson<WeeklyPulse>("/api/v1/pulse/generate", {
        method: "POST",
        body: JSON.stringify({ use_fixture: true, lookback_weeks: 8 }),
      });
      setActionMsg("Generated a new pulse (fixture run).");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Failed to generate pulse");
    } finally {
      setActionBusy("none");
    }
  }, [load]);

  const subscribe = useCallback(async () => {
    setActionBusy("subscribe");
    setActionMsg(null);
    try {
      await fetchJson<{ email: string; status: string; updated_at: string }>("/api/v1/pulse/subscribe", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setActionMsg("Subscribed successfully.");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Subscription failed");
    } finally {
      setActionBusy("none");
    }
  }, [email, load]);

  const unsubscribe = useCallback(async () => {
    setActionBusy("unsubscribe");
    setActionMsg(null);
    try {
      await fetchJson<{ email: string; status: string; updated_at: string }>("/api/v1/pulse/unsubscribe", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setActionMsg("Unsubscribed successfully.");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Unsubscribe failed");
    } finally {
      setActionBusy("none");
    }
  }, [email, load]);

  const canAct = email.trim().length > 3 && actionBusy === "none";

  const statusTone = useMemo(() => {
    if (loading) return "neutral" as const;
    if (error) return "danger" as const;
    if (!idealCurrent) return "warning" as const;
    if (idealCurrent.degraded) return "warning" as const;
    return "success" as const;
  }, [error, idealCurrent, loading]);

  if (loading) return <LoadingState label="Loading pulse data…" />;
  if (error) return <ErrorState title="Pulse API error" message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Weekly Pulse</h2>
            <p className="mt-1 text-sm text-slate-400">Current pulse + history, fully backend-driven (Phase 2).</p>
          </div>
          <div className="flex items-center gap-3">
            <InlineStatus
              tone={statusTone}
              label={
                idealCurrent
                  ? `Current pulse: ${idealCurrent.pulse_id} · ${formatShortIso(idealCurrent.created_at)}`
                  : "No pulse yet"
              }
            />
            <button
              type="button"
              className="rounded-md bg-groww-accent px-3 py-2 text-xs font-semibold text-groww-ink hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
              onClick={() => void generateFixture()}
              disabled={actionBusy !== "none"}
            >
              {actionBusy === "generate" ? "Generating…" : "Generate (fixture)"}
            </button>
          </div>
        </div>

        {actionMsg ? <p className="mt-3 text-sm text-slate-200">{actionMsg}</p> : null}

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-md border border-groww-border/70 bg-groww-ink/40 p-3">
            <div className="text-xs font-semibold text-slate-300">Reviews considered</div>
            <div className="mt-1 text-xl font-semibold text-white">{idealCurrent?.metrics.reviews_considered ?? "—"}</div>
          </div>
          <div className="rounded-md border border-groww-border/70 bg-groww-ink/40 p-3">
            <div className="text-xs font-semibold text-slate-300">Average rating</div>
            <div className="mt-1 text-xl font-semibold text-white">
              {idealCurrent ? idealCurrent.metrics.average_rating.toFixed(2) : "—"}
            </div>
          </div>
          <div className="rounded-md border border-groww-border/70 bg-groww-ink/40 p-3">
            <div className="text-xs font-semibold text-slate-300">Lookback window</div>
            <div className="mt-1 text-xl font-semibold text-white">
              {idealCurrent ? `${idealCurrent.metrics.lookback_weeks}w` : "—"}
            </div>
          </div>
        </div>

        {idealCurrent ? (
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-groww-border bg-groww-ink/30 p-4">
              <h3 className="text-sm font-semibold text-white">Themes</h3>
              <div className="mt-3 space-y-3">
                {idealCurrent.themes.map((t) => (
                  <div key={t.theme} className="rounded-md border border-groww-border/60 bg-groww-panel/40 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-semibold text-slate-100">{t.theme}</div>
                      <div className="text-xs text-slate-400">{t.count} mentions</div>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">{t.summary}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-groww-border bg-groww-ink/30 p-4">
              <h3 className="text-sm font-semibold text-white">Recommended actions</h3>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-200">
                {idealCurrent.recommended_actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
              {idealCurrent.degraded ? (
                <p className="mt-4 text-xs text-amber-200">
                  Degraded mode: {idealCurrent.degraded_reason ?? "LLM keys missing or provider unavailable."}
                </p>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-400">
            No pulse exists yet. Generate a fixture pulse to validate the full Phase 2 path end-to-end.
          </p>
        )}
      </div>

      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <h3 className="text-sm font-semibold text-white">Subscription</h3>
        <p className="mt-1 text-sm text-slate-400">Subscribe/unsubscribe for weekly pulse emails (sending is Phase 7).</p>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="pm@example.com"
            className="w-full rounded-md border border-groww-border bg-groww-ink/50 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent md:max-w-sm"
            aria-label="Subscription email"
          />
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-md bg-white/10 px-3 py-2 text-xs font-semibold text-white hover:bg-white/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
              onClick={() => void subscribe()}
              disabled={!canAct}
            >
              {actionBusy === "subscribe" ? "Subscribing…" : "Subscribe"}
            </button>
            <button
              type="button"
              className="rounded-md border border-groww-border bg-groww-ink/40 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-groww-accent disabled:opacity-50"
              onClick={() => void unsubscribe()}
              disabled={!canAct}
            >
              {actionBusy === "unsubscribe" ? "Unsubscribing…" : "Unsubscribe"}
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-groww-border bg-groww-panel p-4">
        <h3 className="text-sm font-semibold text-white">Pulse history</h3>
        <p className="mt-1 text-sm text-slate-400">Last 10 pulses stored (newest first).</p>
        <div className="mt-4 overflow-hidden rounded-lg border border-groww-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-groww-ink/40 text-xs text-slate-300">
              <tr>
                <th className="px-3 py-2">Pulse</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Reviews</th>
                <th className="px-3 py-2">Avg rating</th>
                <th className="px-3 py-2">Mode</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-groww-border">
              {historyRows.map((p) => (
                <tr key={p.pulse_id} className="bg-groww-panel/30">
                  <td className="px-3 py-2 font-medium text-slate-100">{p.pulse_id}</td>
                  <td className="px-3 py-2 text-slate-300">{formatShortIso(p.created_at)}</td>
                  <td className="px-3 py-2 text-slate-300">{p.metrics.reviews_considered}</td>
                  <td className="px-3 py-2 text-slate-300">{p.metrics.average_rating.toFixed(2)}</td>
                  <td className="px-3 py-2 text-slate-300">{p.degraded ? "Degraded" : "LLM"}</td>
                </tr>
              ))}
              {historyRows.length === 0 ? (
                <tr className="bg-groww-panel/30">
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-400">
                    No pulses yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
