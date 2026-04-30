-- Phase 6: Advisor HITL approval workflow
-- Additive migration — does not modify any existing table (Rules D4).
-- Apply after phase5_schema.sql.

-- ─────────────────────────────────────────────────────────────────────────────
-- No new tables required for Phase 6.
--
-- The Phase 5 schema (phase5_schema.sql) already provides:
--
--   bookings       — status column tracks PENDING_ADVISOR_APPROVAL → APPROVED
--                    / REJECTED transitions.  The bookings_status_idx index
--                    (phase5_schema.sql) makes advisor pending/upcoming list
--                    queries fast.
--
--   booking_events — immutable audit log.  Each approve/reject call writes a row
--                    with from_status, to_status, reason, and actor.  This is
--                    sufficient to reconstruct the full approval audit trail
--                    without a dedicated advisor_approvals table (Rules D3, W9,
--                    P6.5).
--
-- The actor column (already present in booking_events) now receives the value
-- "advisor" on approve/reject writes, distinguishing advisor actions from
-- "system" actions in the audit trail.
--
-- If a future phase requires querying advisor-specific metadata that cannot be
-- derived from booking_events (e.g. per-advisor statistics, SLA tracking), an
-- advisor_approvals or advisor_actions table should be added as a new additive
-- migration at that time.
-- ─────────────────────────────────────────────────────────────────────────────

-- Confirm bookings_status_idx exists (from phase5_schema.sql); create if missing
-- to keep this migration safe to re-run in environments where phase5 was partial.
CREATE INDEX IF NOT EXISTS bookings_status_idx
    ON bookings (status);

-- Composite index for upcoming list query (APPROVED + CONFIRMATION_SENT, ordered).
-- Covers: SELECT * FROM bookings WHERE status IN ('approved','confirmation_sent')
--         ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS bookings_status_created_at_idx
    ON bookings (status, created_at DESC);
