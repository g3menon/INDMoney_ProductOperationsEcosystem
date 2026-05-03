"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { fetchJson } from "@/lib/api-client";
import { formatShortIso } from "@/lib/formatters";

type AdvisorBookingItem = {
  booking_id: string;
  customer_name: string;
  issue_summary: string;
  preferred_date: string;
  preferred_time: string;
  status: string;
  display_timezone: string;
  created_at: string;
};

type BookingList = {
  items: AdvisorBookingItem[];
  count: number;
};

type WeeklyPulse = {
  themes: { theme: string; summary: string; count: number }[];
};

type AdvisorView = "pending" | "upcoming" | "archive";

function statusLabel(status: string) {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function slotLabel(item: AdvisorBookingItem) {
  return `${item.preferred_date} at ${item.preferred_time} IST`;
}

function bookingReason(item: AdvisorBookingItem) {
  const [reason] = item.issue_summary.split(":");
  return reason && reason.length < 40 ? reason : "Advisor support";
}

function bookingContext(item: AdvisorBookingItem) {
  const [, ...rest] = item.issue_summary.split(":");
  return (rest.join(":") || item.issue_summary).replace(/^ Chat summary:\s*/i, "").trim();
}

function isSameDate(date: string, offsetDays: number) {
  const target = new Date();
  target.setDate(target.getDate() + offsetDays);
  return date === target.toISOString().slice(0, 10);
}

function groupUpcoming(items: AdvisorBookingItem[]) {
  return [
    { label: "Today", items: items.filter((item) => isSameDate(item.preferred_date, 0)) },
    { label: "Tomorrow", items: items.filter((item) => isSameDate(item.preferred_date, 1)) },
    {
      label: "Later this week",
      items: items.filter((item) => !isSameDate(item.preferred_date, 0) && !isSameDate(item.preferred_date, 1)),
    },
  ];
}

function CopyableId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="focus-ring inline-flex items-center gap-2 rounded-full border border-groww-border bg-white px-3 py-1.5 font-mono text-xs font-semibold text-groww-accent shadow-sm"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      }}
    >
      {value}
      <span className="font-sans text-[10px] text-groww-faint">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function StatusDot({ status }: { status: string }) {
  const tone =
    status.includes("approved") || status.includes("confirmation")
      ? "bg-groww-success"
      : status.includes("rejected")
        ? "bg-groww-danger"
        : "bg-groww-warning";
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-groww-surfaceSoft px-3 py-1 text-xs font-semibold text-groww-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${tone}`} aria-hidden />
      {statusLabel(status)}
    </span>
  );
}

function EmailPreview({ item }: { item: AdvisorBookingItem }) {
  return (
    <div className="mt-4 rounded-2xl border border-groww-border bg-groww-surfaceSoft p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-groww-faint">Confirmation email preview</p>
      <h4 className="mt-2 text-sm font-semibold text-groww-text">
        Your advisory session has been confirmed - {item.preferred_date} at {item.preferred_time}
      </h4>
      <div className="mt-3 rounded-xl bg-white p-4 text-sm leading-6 text-groww-muted shadow-sm">
        <p>Hi {item.customer_name},</p>
        <p className="mt-2">
          Your Groww advisor session is confirmed for {slotLabel(item)}. We will use the booking ID {item.booking_id}
          for any follow-up.
        </p>
        <p className="mt-2">Booking reason: {bookingReason(item)}</p>
        <p className="mt-2">Context for the advisor: {bookingContext(item)}</p>
      </div>
    </div>
  );
}

export function AdvisorTab() {
  const [view, setView] = useState<AdvisorView>("pending");
  const [pending, setPending] = useState<AdvisorBookingItem[]>([]);
  const [upcoming, setUpcoming] = useState<AdvisorBookingItem[]>([]);
  const [archive, setArchive] = useState<AdvisorBookingItem[]>([]);
  const [themes, setThemes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [expandedEmailId, setExpandedEmailId] = useState<string | null>(null);
  const [declineId, setDeclineId] = useState<string | null>(null);
  const [declineReason, setDeclineReason] = useState("");
  const [archiveQuery, setArchiveQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingResponse, upcomingResponse, pulseResponse] = await Promise.all([
        fetchJson<BookingList>("/api/v1/advisor/pending"),
        fetchJson<BookingList>("/api/v1/advisor/upcoming"),
        fetchJson<WeeklyPulse | null>("/api/v1/pulse/current").catch(() => ({ success: true, data: null })),
      ]);
      setPending(pendingResponse.data?.items ?? []);
      setUpcoming(upcomingResponse.data?.items ?? []);
      setThemes((pulseResponse.data?.themes ?? []).slice(0, 4).map((theme) => theme.theme));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Advisor console could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = useCallback(
    async (item: AdvisorBookingItem) => {
      setBusyId(item.booking_id);
      setSuccess(null);
      try {
        await fetchJson(`/api/v1/advisor/approve/${item.booking_id}`, {
          method: "POST",
          body: JSON.stringify({ actor: "advisor", reason: "Advisor approved from console." }),
        });
        setPending((items) => items.filter((row) => row.booking_id !== item.booking_id));
        const approved = { ...item, status: "approved" };
        setUpcoming((items) => [approved, ...items]);
        setArchive((items) => [approved, ...items]);
        setSuccess(`${item.booking_id} approved. Customer confirmation can now be sent.`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Approval could not be completed.");
      } finally {
        setBusyId(null);
      }
    },
    [],
  );

  const decline = useCallback(
    async (item: AdvisorBookingItem) => {
      if (!declineReason.trim()) return;
      setBusyId(item.booking_id);
      setSuccess(null);
      try {
        await fetchJson(`/api/v1/advisor/reject/${item.booking_id}`, {
          method: "POST",
          body: JSON.stringify({ actor: "advisor", reason: declineReason.trim() }),
        });
        const rejected = { ...item, status: "rejected" };
        setPending((items) => items.filter((row) => row.booking_id !== item.booking_id));
        setArchive((items) => [rejected, ...items]);
        setSuccess(`${item.booking_id} declined.`);
        setDeclineId(null);
        setDeclineReason("");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Decline could not be completed.");
      } finally {
        setBusyId(null);
      }
    },
    [declineReason],
  );

  const groupedUpcoming = useMemo(() => groupUpcoming(upcoming), [upcoming]);
  const filteredArchive = useMemo(() => {
    const rows = [...archive, ...upcoming].filter(
      (item, index, all) => all.findIndex((row) => row.booking_id === item.booking_id) === index,
    );
    const query = archiveQuery.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter(
      (item) =>
        item.booking_id.toLowerCase().includes(query) ||
        item.customer_name.toLowerCase().includes(query) ||
        item.issue_summary.toLowerCase().includes(query),
    );
  }, [archive, upcoming, archiveQuery]);

  if (loading) return <LoadingState label="Loading advisor console" />;
  if (error && pending.length === 0 && upcoming.length === 0) {
    return <ErrorState title="Advisor console needs attention" message={error} onRetry={() => void load()} />;
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <aside className="soft-card h-fit p-5 xl:sticky xl:top-5">
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-groww-accent">Advisor Console</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-groww-text">Review requests and prepare for calls</h2>
        <p className="mt-3 text-sm leading-6 text-groww-muted">
          Approve booking requests only after reviewing customer context and the proposed confirmation email.
        </p>

        <div className="mt-6 grid grid-cols-3 gap-2">
          {[
            { label: "Pending", value: pending.length },
            { label: "Today", value: groupedUpcoming[0]?.items.length ?? 0 },
            { label: "This week", value: upcoming.length },
          ].map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-groww-border bg-groww-surfaceSoft p-3 text-center">
              <p className="text-xl font-semibold text-groww-text">{stat.value}</p>
              <p className="mt-1 text-[11px] font-semibold text-groww-muted">{stat.label}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 border-t border-groww-border pt-5">
          <p className="text-sm font-semibold text-groww-text">Top customer intents this week</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(themes.length ? themes : ["Fee clarity", "Fund comparison", "Advisor booking"]).map((theme) => (
              <span key={theme} className="pill-chip">
                {theme}
              </span>
            ))}
          </div>
          <button
            type="button"
            className="focus-ring mt-4 rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          >
            Open Product pulse view
          </button>
        </div>
      </aside>

      <section className="soft-card min-w-0 p-4 md:p-5">
        <div className="flex flex-col gap-4 border-b border-groww-border pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-groww-text">Booking operations</h3>
            <p className="mt-1 text-sm text-groww-muted">Approve, decline, or review customer context before the call.</p>
          </div>
          <div className="flex rounded-full border border-groww-border bg-groww-surfaceSoft p-1">
            {[
              ["pending", "Pending Requests"],
              ["upcoming", "Upcoming Calls"],
              ["archive", "Booking Archive"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={
                  view === id
                    ? "focus-ring rounded-full bg-white px-3 py-2 text-xs font-semibold text-groww-text shadow-sm"
                    : "focus-ring rounded-full px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-text"
                }
                onClick={() => setView(id as AdvisorView)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {success ? <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p> : null}
        {error ? <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

        {view === "pending" ? (
          <div className="mt-4 divide-y divide-groww-border">
            {pending.map((item) => (
              <article key={item.booking_id} className="py-4">
                <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <CopyableId value={item.booking_id} />
                      <StatusDot status={item.status} />
                    </div>
                    <h4 className="mt-3 font-semibold text-groww-text">{item.customer_name}</h4>
                    <p className="mt-1 text-sm font-medium text-groww-muted">{slotLabel(item)}</p>
                    <p className="mt-2 text-sm font-semibold text-groww-text">Reason: {bookingReason(item)}</p>
                    <p className="mt-1 max-w-3xl text-sm leading-6 text-groww-muted">{bookingContext(item)}</p>
                    <p className="mt-2 text-xs text-groww-faint">Created {formatShortIso(item.created_at)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <button
                      type="button"
                      className="focus-ring rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent"
                      onClick={() => setExpandedEmailId((current) => (current === item.booking_id ? null : item.booking_id))}
                    >
                      Preview email
                    </button>
                    <button
                      type="button"
                      className="focus-ring rounded-full bg-groww-accent px-3 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-50"
                      onClick={() => void approve(item)}
                      disabled={busyId === item.booking_id}
                    >
                      {busyId === item.booking_id ? "Approving..." : "Approve"}
                    </button>
                    <button
                      type="button"
                      className="focus-ring rounded-full border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50"
                      onClick={() => setDeclineId((current) => (current === item.booking_id ? null : item.booking_id))}
                      disabled={busyId === item.booking_id}
                    >
                      Decline
                    </button>
                  </div>
                </div>
                {expandedEmailId === item.booking_id ? <EmailPreview item={item} /> : null}
                {declineId === item.booking_id ? (
                  <div className="mt-4 rounded-2xl border border-red-100 bg-red-50 p-4">
                    <label className="text-xs font-semibold text-red-700" htmlFor={`decline-${item.booking_id}`}>
                      Decline reason
                    </label>
                    <textarea
                      id={`decline-${item.booking_id}`}
                      value={declineReason}
                      onChange={(event) => setDeclineReason(event.target.value)}
                      className="focus-ring mt-2 min-h-[80px] w-full rounded-xl border border-red-100 bg-white px-3 py-2 text-sm text-groww-text"
                      placeholder="Add a brief reason for the customer support trail."
                    />
                    <div className="mt-3 flex justify-end gap-2">
                      <button
                        type="button"
                        className="focus-ring rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted"
                        onClick={() => setDeclineId(null)}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="focus-ring rounded-full bg-red-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                        onClick={() => void decline(item)}
                        disabled={!declineReason.trim() || busyId === item.booking_id}
                      >
                        Confirm decline
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
            {pending.length === 0 ? (
              <div className="py-12 text-center">
                <h4 className="font-semibold text-groww-text">No pending approvals</h4>
                <p className="mt-2 text-sm text-groww-muted">New customer booking requests will appear here for advisor review.</p>
              </div>
            ) : null}
          </div>
        ) : null}

        {view === "upcoming" ? (
          <div className="mt-4 space-y-5">
            {groupedUpcoming.map((group) => (
              <div key={group.label}>
                <h4 className="text-sm font-semibold text-groww-text">{group.label}</h4>
                <div className="mt-3 divide-y divide-groww-border rounded-2xl border border-groww-border bg-white">
                  {group.items.map((item) => (
                    <div key={item.booking_id} className="grid gap-3 p-4 md:grid-cols-[92px_1fr_auto] md:items-center">
                      <p className="font-semibold text-groww-text">{item.preferred_time}</p>
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <CopyableId value={item.booking_id} />
                          <StatusDot status={item.status} />
                        </div>
                        <p className="mt-2 text-sm font-semibold text-groww-text">Reason: {bookingReason(item)}</p>
                        <p className="mt-1 text-sm leading-6 text-groww-muted">{bookingContext(item)}</p>
                      </div>
                      <button
                        type="button"
                        className="focus-ring rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-muted hover:text-groww-accent"
                        onClick={() => setExpandedEmailId((current) => (current === item.booking_id ? null : item.booking_id))}
                      >
                        View context
                      </button>
                      {expandedEmailId === item.booking_id ? (
                        <div className="md:col-span-3">
                          <EmailPreview item={item} />
                        </div>
                      ) : null}
                    </div>
                  ))}
                  {group.items.length === 0 ? <p className="p-4 text-sm text-groww-muted">No calls in this group.</p> : null}
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {view === "archive" ? (
          <div className="mt-4">
            <input
              value={archiveQuery}
              onChange={(event) => setArchiveQuery(event.target.value)}
              placeholder="Search booking ID, customer, or context"
              className="focus-ring w-full rounded-xl border border-groww-border bg-white px-3 py-3 text-sm text-groww-text placeholder:text-groww-faint"
            />
            <div className="mt-4 overflow-hidden rounded-2xl border border-groww-border bg-white">
              <div className="hidden gap-3 border-b border-groww-border bg-groww-surfaceSoft px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-groww-faint md:grid md:grid-cols-[1.1fr_1fr_1fr_0.9fr]">
                <span>Booking ID</span>
                <span>Created</span>
                <span>Scheduled</span>
                <span>Status</span>
              </div>
              <div className="divide-y divide-groww-border">
                {filteredArchive.map((item) => (
                  <div key={item.booking_id} className="grid gap-3 px-4 py-4 text-sm md:grid-cols-[1.1fr_1fr_1fr_0.9fr] md:items-center">
                    <CopyableId value={item.booking_id} />
                    <span className="text-groww-muted">{formatShortIso(item.created_at)}</span>
                    <span className="text-groww-muted">{slotLabel(item)}</span>
                    <StatusDot status={item.status} />
                  </div>
                ))}
                {filteredArchive.length === 0 ? (
                  <p className="px-4 py-8 text-center text-sm text-groww-muted">
                    Archive rows appear after approvals or declines in this console.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
