"use client";

import { useState } from "react";

export type BookingSummary = {
  booking_id: string;
  preferred_date?: string;
  preferred_time?: string;
  display_timezone?: string;
  status?: string;
  issue_summary?: string;
  booking_reason?: string;
};

export function BookingCard({ booking }: { booking: BookingSummary }) {
  const [copied, setCopied] = useState(false);
  const slot = [booking.preferred_date, booking.preferred_time].filter(Boolean).join(" at ");

  const copyBookingId = async () => {
    await navigator.clipboard.writeText(booking.booking_id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="mt-3 rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-groww-success" aria-hidden />
            Pending advisor approval
          </div>
          <h4 className="mt-3 text-sm font-semibold text-groww-text">Advisor request created</h4>
          {slot ? (
            <p className="mt-1 text-sm text-groww-muted">
              Requested slot: {slot} {booking.display_timezone ?? "IST"}
            </p>
          ) : null}
          {booking.booking_reason ? (
            <p className="mt-2 text-sm font-semibold text-groww-text">Reason: {booking.booking_reason}</p>
          ) : null}
          {booking.issue_summary ? <p className="mt-2 text-sm leading-6 text-groww-muted">{booking.issue_summary}</p> : null}
        </div>
        <button
          type="button"
          className="focus-ring rounded-full border border-groww-border bg-white px-3 py-2 text-xs font-semibold text-groww-accent shadow-sm hover:bg-groww-accentSoft"
          onClick={() => void copyBookingId()}
        >
          {copied ? "Copied" : "Copy ID"}
        </button>
      </div>
      <div className="mt-4 rounded-xl border border-groww-border bg-white px-3 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-groww-faint">Booking ID</p>
        <p className="mt-1 font-mono text-sm font-semibold text-groww-text">{booking.booking_id}</p>
      </div>
    </div>
  );
}
