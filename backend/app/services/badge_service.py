"""Badge computation (Phase 1: deterministic zeros + connectivity flag)."""

from __future__ import annotations

from app.core.config import Settings
from app.integrations.supabase.client import check_supabase_connectivity
from app.repositories.pulse_repository import get_pulse_repository
from app.repositories.subscription_repository import get_subscription_repository
from app.schemas.dashboard import AdvisorBadges, BadgePayload, CustomerBadges, ProductBadges


async def compute_badges(settings: Settings) -> BadgePayload:
    """
    Backend-owned badge state (`Docs/Architecture.md`).
    Later phases replace zeros with repository-backed counts.
    """
    ok, _ = await check_supabase_connectivity(settings)
    # Phase 2: fill a couple Product badge signals from backend state.
    pulse_repo = get_pulse_repository(settings)
    subs_repo = get_subscription_repository(settings)
    current = await pulse_repo.get_current_pulse()
    active_subs = await subs_repo.count_active()
    return BadgePayload(
        customer=CustomerBadges(
            booking_in_progress=0,
            follow_up_available=0,
            voice_ready=False,
        ),
        product=ProductBadges(
            pulse_ready=bool(current),
            active_subscribers=active_subs,
            next_scheduled_send_ist=None,
            send_failure_warning=False,
        ),
        advisor=AdvisorBadges(
            pending_approvals=0,
            upcoming_bookings_today=0,
            recently_rejected=0,
            cancellations_to_review=0,
        ),
        supabase_connected=ok,
    )
