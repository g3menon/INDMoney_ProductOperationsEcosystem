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

const OWNER_POOL = ["PM", "Ops", "Support", "Advisor Enablement"];

function themeCode(theme: string, index: number) {
  const lower = theme.toLowerCase();
  const prefix = lower.includes("trust")
    ? "TRUST"
    : lower.includes("performance") || lower.includes("slow")
      ? "PERF"
      : lower.includes("advisor") || lower.includes("booking")
        ? "ADV"
        : lower.includes("fee") || lower.includes("charge")
          ? "FEE"
          : "UX";
  return `${prefix}-${String(index + 1).padStart(2, "0")}`;
}

function actionTitle(action: string) {
  const trimmed = action.replace(/\.$/, "");
  if (trimmed.length <= 72) return trimmed;
  return `${trimmed.slice(0, 69)}...`;
}

function actionBody(action: string) {
  if (action.length > 72) return action;
  return `Turn this signal into a scoped product or operations follow-up, with a clear owner and measurable next step.`;
}

function inferBookingReasons(pulse: WeeklyPulse | null) {
  const themes = pulse?.themes ?? [];
  const total = Math.max(
    themes.reduce((sum, theme) => sum + Math.max(theme.count, 0), 0),
    1,
  );
  const source = themes.length
    ? themes.slice(0, 4)
    : [
        { theme: "Fee clarity", summary: "Customers need reassurance before acting on fund costs.", count: 8 },
        { theme: "Fund comparison", summary: "Customers want advisor help choosing between similar options.", count: 6 },
        { theme: "Trust and next steps", summary: "Users need confidence on the right action after reading insights.", count: 5 },
      ];

  return source.map((theme) => ({
    category: theme.theme,
    count: theme.count,
    percent: Math.max(12, Math.round((theme.count / total) * 100)),
    explanation: theme.summary,
  }));
}

function Stars({ rating }: { rating: number }) {
  return <span className="text-xs font-semibold text-amber-500">{"*".repeat(Math.max(1, Math.min(5, rating)))}</span>;
}

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
      const [currentPulse, pulseHistory] = await Promise.all([
        fetchJson<WeeklyPulse | null>("/api/v1/pulse/current"),
        fetchJson<WeeklyPulse[]>("/api/v1/pulse/history?limit=10"),
      ]);
      setCurrent(currentPulse);
      setHistory(pulseHistory);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Weekly Pulse could not be loaded.");
      setCurrent(null);
      setHistory(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pulse = current?.data ?? null;
  const historyRows = history?.data ?? [];
  const bookingReasons = useMemo(() => inferBookingReasons(pulse), [pulse]);
  const maxThemeCount = Math.max(...(pulse?.themes ?? []).map((theme) => theme.count), 1);
  const topTheme = pulse?.themes?.[0]?.theme ?? "Awaiting signal";
  const inferredDemand = bookingReasons.reduce((sum, item) => sum + item.count, 0);

  const generateSample = useCallback(async () => {
    setActionBusy("generate");
    setActionMsg(null);
    try {
      await fetchJson<WeeklyPulse>("/api/v1/pulse/generate", {
        method: "POST",
        body: JSON.stringify({ use_fixture: true, lookback_weeks: 8 }),
      });
      setActionMsg("Sample pulse generated for local review.");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Sample pulse could not be generated.");
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
      setActionMsg("Subscription saved. The current pulse will be included in the weekly email.");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Subscription could not be saved.");
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
      setActionMsg("Subscription paused for this email.");
      await load();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "Subscription could not be updated.");
    } finally {
      setActionBusy("none");
    }
  }, [email, load]);

  const canAct = email.trim().length > 3 && actionBusy === "none";

  const statusTone = useMemo(() => {
    if (loading) return "neutral" as const;
    if (error) return "danger" as const;
    if (!pulse) return "warning" as const;
    if (pulse.degraded) return "warning" as const;
    return "success" as const;
  }, [error, pulse, loading]);

  if (loading) return <LoadingState label="Loading Weekly Pulse" />;
  if (error) return <ErrorState title="Weekly Pulse needs attention" message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-5">
      <section className="gradient-halo rounded-[2rem] border border-white/80 p-6 shadow-soft">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap gap-2">
              <InlineStatus tone={statusTone} label={pulse ? "Latest pulse ready" : "No pulse yet"} />
              <span className="pill-chip">Every Monday - 10:00 AM IST</span>
            </div>
            <h2 className="mt-5 text-4xl font-semibold tracking-tight text-groww-text">Weekly Pulse</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-groww-muted">
              Insights from customer questions, reviews, and advisor demand.
            </p>
            {pulse ? (
              <p className="mt-3 text-xs font-semibold text-groww-faint">
                Pulse {pulse.pulse_id} - refreshed {formatShortIso(pulse.created_at)}
              </p>
            ) : null}
          </div>
          <div className="rounded-2xl border border-groww-border bg-white/85 p-4 shadow-card">
            <p className="text-xs font-semibold text-groww-faint">Next scheduled send</p>
            <p className="mt-1 text-lg font-semibold text-groww-text">Monday, 10:00 AM IST</p>
            <p className="mt-1 text-xs text-groww-muted">Subscribers receive the same pulse shown here.</p>
          </div>
        </div>

        {pulse?.degraded ? (
          <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Analysis is in degraded mode. Only {pulse.metrics.reviews_considered} reviews were available in this run.
            {pulse.degraded_reason ? <span className="block pt-1 text-amber-700">{pulse.degraded_reason}</span> : null}
          </div>
        ) : null}
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Reviews analyzed", value: pulse?.metrics.reviews_considered ?? 0, detail: "Cleaned review inputs", accent: false },
          { label: "Average rating", value: pulse ? pulse.metrics.average_rating.toFixed(2) : "0.00", detail: "Across reviewed inputs", accent: false },
          { label: "Top issue theme", value: topTheme, detail: "Highest mention cluster", accent: true },
          { label: "Advisor booking intent", value: inferredDemand, detail: "Inferred from current themes", accent: false },
        ].map((card) => (
          <div
            key={card.label}
            className={
              card.accent
                ? "rounded-2xl border border-violet-100 bg-gradient-to-br from-groww-accentSoft to-white p-5 shadow-card"
                : "soft-card p-5"
            }
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-xs font-bold text-groww-accent shadow-sm">
              {card.label.slice(0, 2).toUpperCase()}
            </div>
            <p className="mt-4 text-xs font-semibold uppercase tracking-[0.14em] text-groww-faint">{card.label}</p>
            <p className="mt-2 line-clamp-2 text-2xl font-semibold tracking-tight text-groww-text">{card.value}</p>
            <p className="mt-1 text-sm text-groww-muted">{card.detail}</p>
          </div>
        ))}
      </section>

      <section className="soft-card p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-groww-text">This week in summary</h3>
            <p className="mt-1 text-sm text-groww-muted">Executive narrative for PM and operations review.</p>
          </div>
        </div>
        <div className="mt-4 rounded-2xl bg-groww-surfaceSoft p-5 text-base leading-8 text-groww-text">
          {pulse?.narrative ??
            "No pulse has been generated yet. Once review ingestion and pulse generation complete, this section will summarize the main customer themes and operational opportunities."}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="soft-card p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-groww-text">Pulse themes</h3>
              <p className="mt-1 text-sm text-groww-muted">Issue clusters with PM-ready context and intensity.</p>
            </div>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {(pulse?.themes ?? []).map((theme, index) => {
              const intensity = Math.max(8, Math.round((theme.count / maxThemeCount) * 100));
              return (
                <article key={theme.theme} className="rounded-2xl border border-groww-border bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-groww-text">{theme.theme}</p>
                      <p className="mt-1 font-mono text-xs font-semibold text-groww-accent">{themeCode(theme.theme, index)}</p>
                    </div>
                    <span className="rounded-full bg-groww-surfaceSoft px-3 py-1 text-xs font-semibold text-groww-muted">
                      {theme.count} mentions
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-groww-muted">{theme.summary}</p>
                  <p className="mt-3 text-xs font-semibold text-groww-text">Why this matters</p>
                  <p className="mt-1 text-sm leading-6 text-groww-muted">
                    This signal can affect trust, completion, or advisor demand if the same question repeats across channels.
                  </p>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-groww-surfaceSoft">
                    <div className="h-full rounded-full bg-groww-accent" style={{ width: `${intensity}%` }} />
                  </div>
                </article>
              );
            })}
            {!pulse || pulse.themes.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-groww-border bg-white p-6 text-sm text-groww-muted md:col-span-2">
                Theme cards appear after a pulse is generated from review inputs.
              </div>
            ) : null}
          </div>
        </div>

        <div className="soft-card p-5">
          <h3 className="text-lg font-semibold text-groww-text">Why customers are booking advisors</h3>
          <p className="mt-1 text-sm text-groww-muted">Inferred from pulse themes until direct booking analytics are available.</p>
          <div className="mt-5 space-y-4">
            {bookingReasons.map((reason) => (
              <div key={reason.category}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-semibold text-groww-text">{reason.category}</span>
                  <span className="text-groww-muted">{reason.count}</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-groww-surfaceSoft">
                  <div className="h-full rounded-full bg-groww-accentBlue" style={{ width: `${reason.percent}%` }} />
                </div>
                <p className="mt-2 text-xs leading-5 text-groww-muted">{reason.explanation}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="soft-card p-5">
          <h3 className="text-lg font-semibold text-groww-text">Voice of customer</h3>
          <p className="mt-1 text-sm text-groww-muted">Representative quotes from the current pulse.</p>
          <div className="mt-5 grid gap-3">
            {(pulse?.quotes ?? []).slice(0, 6).map((quote, index) => (
              <article key={quote.review_id} className="rounded-2xl border border-groww-border bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs font-semibold text-groww-accent">VOC-{String(index + 1).padStart(2, "0")}</span>
                  <Stars rating={quote.rating} />
                </div>
                <p className="mt-3 text-sm leading-6 text-groww-text">"{quote.quote}"</p>
                <p className="mt-3 text-xs text-groww-faint">Review {quote.review_id}</p>
              </article>
            ))}
            {!pulse || pulse.quotes.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-groww-border bg-white p-6 text-sm text-groww-muted">
                Customer quotes appear here after the pulse has review context.
              </div>
            ) : null}
          </div>
        </div>

        <div className="soft-card p-5">
          <h3 className="text-lg font-semibold text-groww-text">Recommended actions</h3>
          <p className="mt-1 text-sm text-groww-muted">Prioritized follow-ups for PM, Ops, Support, and advisor teams.</p>
          <div className="mt-5 space-y-3">
            {(pulse?.recommended_actions ?? []).map((action, index) => (
              <article key={action} className="rounded-2xl border border-groww-border bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-groww-accentSoft px-3 py-1 text-xs font-semibold text-groww-accent">
                    P{Math.min(index + 1, 3)}
                  </span>
                  <span className="rounded-full bg-groww-surfaceSoft px-3 py-1 text-xs font-semibold text-groww-muted">
                    Owner: {OWNER_POOL[index % OWNER_POOL.length]}
                  </span>
                </div>
                <h4 className="mt-3 text-sm font-semibold text-groww-text">{actionTitle(action)}</h4>
                <p className="mt-2 text-sm leading-6 text-groww-muted">{actionBody(action)}</p>
                <button
                  type="button"
                  className="focus-ring mt-3 rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent"
                >
                  Add to backlog
                </button>
              </article>
            ))}
            {!pulse || pulse.recommended_actions.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-groww-border bg-white p-6 text-sm text-groww-muted">
                Action cards appear after the pulse is generated.
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="soft-card p-5">
          <h3 className="text-lg font-semibold text-groww-text">Email subscription</h3>
          <p className="mt-1 text-sm leading-6 text-groww-muted">
            Subscribe PM stakeholders to the weekly pulse email. Next send: Monday at 10:00 AM IST.
          </p>
          <div className="mt-5 space-y-3">
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="pm@example.com"
              className="focus-ring w-full rounded-xl border border-groww-border bg-white px-3 py-3 text-sm text-groww-text placeholder:text-groww-faint"
              aria-label="Subscription email"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="focus-ring rounded-full bg-groww-accent px-4 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-50"
                onClick={() => void subscribe()}
                disabled={!canAct}
              >
                {actionBusy === "subscribe" ? "Subscribing..." : "Subscribe"}
              </button>
              <button
                type="button"
                className="focus-ring rounded-full border border-groww-border bg-white px-4 py-2 text-xs font-semibold text-groww-muted disabled:opacity-50"
                onClick={() => void unsubscribe()}
                disabled={!canAct}
              >
                {actionBusy === "unsubscribe" ? "Updating..." : "Unsubscribe"}
              </button>
            </div>
            {actionMsg ? <p className="rounded-xl bg-groww-surfaceSoft px-3 py-2 text-sm text-groww-muted">{actionMsg}</p> : null}
          </div>
        </div>

        <div className="soft-card p-5">
          <h3 className="text-lg font-semibold text-groww-text">Pulse history</h3>
          <p className="mt-1 text-sm text-groww-muted">Recent runs with expandable theme and action previews.</p>
          <div className="mt-5 divide-y divide-groww-border">
            {historyRows.map((row) => (
              <details key={row.pulse_id} className="group py-3">
                <summary className="flex cursor-pointer list-none flex-col gap-2 rounded-xl px-2 py-2 hover:bg-groww-surfaceSoft sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-mono text-xs font-semibold text-groww-accent">{row.pulse_id}</p>
                    <p className="mt-1 text-sm text-groww-muted">{formatShortIso(row.created_at)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="pill-chip">{row.metrics.reviews_considered} reviews</span>
                    <span className="pill-chip">{row.degraded ? "Degraded" : "Complete"}</span>
                  </div>
                </summary>
                <div className="px-2 pb-3 pt-2 text-sm leading-6 text-groww-muted">
                  <p>{row.narrative}</p>
                  <p className="mt-2 font-semibold text-groww-text">Themes: {row.themes.map((theme) => theme.theme).join(", ") || "None"}</p>
                </div>
              </details>
            ))}
            {historyRows.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-groww-border bg-white p-6 text-center text-sm text-groww-muted">
                Pulse history appears after the first run is stored.
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {process.env.NODE_ENV === "development" ? (
        <details className="soft-card p-5">
          <summary className="cursor-pointer text-sm font-semibold text-groww-text">Developer tools</summary>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="focus-ring rounded-full border border-groww-border bg-white px-4 py-2 text-xs font-semibold text-groww-muted disabled:opacity-50"
              onClick={() => void generateSample()}
              disabled={actionBusy !== "none"}
            >
              {actionBusy === "generate" ? "Generating..." : "Generate sample pulse"}
            </button>
            <p className="text-xs text-groww-muted">Available locally for visual QA and empty-state testing.</p>
          </div>
        </details>
      ) : null}
    </div>
  );
}
