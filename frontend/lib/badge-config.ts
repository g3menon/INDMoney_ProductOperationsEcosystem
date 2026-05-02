import type { TabId } from "./constants";

export type BadgeCounts = {
  customer: Record<string, number | boolean>;
  product: Record<string, number | boolean | string | null>;
  advisor: Record<string, number | boolean>;
};

export const BADGE_GROUPS: Record<
  TabId,
  { key: string; label: string; description: string }[]
> = {
  customer: [
    { key: "booking_in_progress", label: "Booking in progress", description: "Active booking drafts" },
    { key: "follow_up_available", label: "Follow-ups", description: "Open follow-up items" },
    { key: "voice_ready", label: "Voice ready", description: "Voice capture availability" },
  ],
  product: [
    { key: "pulse_ready", label: "Pulse ready", description: "Latest pulse available for PM review" },
    { key: "active_subscribers", label: "Active subscribers", description: "Weekly pulse email subscribers" },
    { key: "next_scheduled_send_ist", label: "Next send (IST)", description: "Next scheduled weekly send" },
    { key: "send_failure_warning", label: "Send warning", description: "Recent send failures detected" },
  ],
  advisor: [
    { key: "pending_approvals", label: "Pending approvals", description: "Bookings awaiting advisor action" },
    { key: "upcoming_bookings_today", label: "Upcoming today", description: "Confirmed sessions today (IST)" },
    { key: "recently_rejected", label: "Recently rejected", description: "Recent rejections to review" },
    { key: "cancellations_to_review", label: "Cancellations", description: "Cancellation follow-ups" },
  ],
};
