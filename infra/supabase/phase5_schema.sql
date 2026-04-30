-- Phase 5: Booking and customer workflow state
-- Additive migration — does not modify any existing table (Rules D4).
-- Apply after phase1_phase2_schema.sql and phase4_schema.sql.

-- ─────────────────────────────────────────────────────────────────────────────
-- bookings
-- Single source of truth for booking state (Rules W2, D3).
-- Timestamps stored as UTC (Rules D5); display_timezone carries the IST label.
-- booking_id format: BK-YYYYMMDD-XXXX (Architecture.md §Booking architecture).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    booking_id          TEXT        PRIMARY KEY,
    session_id          TEXT        NULL,
    idempotency_key     TEXT        NULL,  -- unique per client submission (G9, D6)
    customer_name       TEXT        NOT NULL,
    customer_email      TEXT        NOT NULL,
    issue_summary       TEXT        NOT NULL,
    preferred_date      DATE        NOT NULL,
    preferred_time      TEXT        NOT NULL,   -- HH:MM 24 h format (IST)
    status              TEXT        NOT NULL DEFAULT 'pending_advisor_approval',
    cancellation_reason TEXT        NULL,
    display_timezone    TEXT        NOT NULL DEFAULT 'Asia/Kolkata (IST)',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency key uniqueness guard (G9).
CREATE UNIQUE INDEX IF NOT EXISTS bookings_idempotency_key_uq
    ON bookings (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Fast lookup by session (Customer tab reconciliation).
CREATE INDEX IF NOT EXISTS bookings_session_id_idx
    ON bookings (session_id)
    WHERE session_id IS NOT NULL;

-- Fast lookup by status (Advisor pending list, Phase 6).
CREATE INDEX IF NOT EXISTS bookings_status_idx
    ON bookings (status);

-- Ordered list of recent bookings.
CREATE INDEX IF NOT EXISTS bookings_created_at_desc_idx
    ON bookings (created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- booking_events
-- Immutable audit log of every state transition (Rules O2, W9, D8).
-- Each row records from_status → to_status so the full lifecycle is
-- reconstructable for debugging and advisor context (Phase 6).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS booking_events (
    event_id    TEXT        PRIMARY KEY,
    booking_id  TEXT        NOT NULL REFERENCES bookings (booking_id),
    from_status TEXT        NULL,   -- NULL for the initial creation event
    to_status   TEXT        NOT NULL,
    reason      TEXT        NULL,
    actor       TEXT        NULL DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS booking_events_booking_id_idx
    ON booking_events (booking_id, created_at DESC);
