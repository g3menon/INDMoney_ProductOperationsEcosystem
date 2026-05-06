"""HTML + plain rendering for Weekly Pulse outbound email.

Mirrors Product tab sections and styling tokens from `frontend/tailwind.config.ts`.
All dynamic fragments are HTML-escaped before interpolation.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.schemas.pulse import PulseTheme, PulseQuote, WeeklyPulse

OWNER_POOL = ["PM", "Ops", "Support", "Advisor Enablement"]

_COLORS = {
    "bg": "#F8F7FC",
    "surface": "#FFFFFF",
    "surfaceSoft": "#F5F3FB",
    "border": "#E8E7F0",
    "text": "#1F2430",
    "muted": "#6B7280",
    "faint": "#9CA3AF",
    "accent": "#7C3AED",
    "accentSoft": "#F3ECFF",
    "accentBlue": "#60A5FA",
    "amberFg": "#92400E",
    "amberBg": "#FFFBEB",
    "amberBorder": "#FDE68A",
}


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _theme_code(theme: str, index: int) -> str:
    lower = theme.lower()
    if "trust" in lower:
        prefix = "TRUST"
    elif "performance" in lower or "slow" in lower:
        prefix = "PERF"
    elif "advisor" in lower or "booking" in lower:
        prefix = "ADV"
    elif "fee" in lower or "charge" in lower:
        prefix = "FEE"
    else:
        prefix = "UX"
    return f"{prefix}-{index + 1:02d}"


def _action_title(action: str) -> str:
    trimmed = action.rstrip(".")
    if len(trimmed) <= 72:
        return trimmed
    return f"{trimmed[:69]}..."


def _action_body(action: str) -> str:
    if len(action) > 72:
        return action
    return (
        "Turn this signal into a scoped product or operations follow-up, with a "
        "clear owner and measurable next step."
    )


def _action_why(action: str) -> str:
    lower = action.lower()
    if "instrument" in lower or "metric" in lower:
        return (
            "Better instrumentation helps PMs separate isolated feedback from "
            "repeatable workflow friction."
        )
    if "support" in lower or "status" in lower:
        return (
            "Clearer customer communication can reduce avoidable support and advisor escalations."
        )
    if "triage" in lower or "owner" in lower:
        return (
            "A named owner prevents recurring review themes from staying as dashboard-only observations."
        )
    return (
        "This converts customer language into a concrete follow-up that can be "
        "tracked by Product Operations."
    )


def _readable_degraded_reason(reason: str | None) -> str:
    if not reason:
        return "The pulse is partial because one or more analysis inputs were unavailable."
    if "low_review_volume" in reason:
        m = re.search(r"low_review_volume:(\d+)", reason)
        count = m.group(1) if m else None
        n = count or "fewer than 150"
        return (
            f"The pulse is partial because {n} reviews were available. Target volume is 150-200 reviews."
        )
    if "groq" in reason:
        return "Theme clustering used the deterministic fallback because the theme provider was unavailable."
    if "gemini" in reason:
        return "Narrative synthesis used a deterministic summary because the writing provider was unavailable."
    return "The pulse is partial, but the available review signals are still shown."


def _infer_booking_reasons(themes: list[PulseTheme]) -> list[dict[str, object]]:
    total = max(sum(max(t.count, 0) for t in themes), 1)
    if themes:
        source = themes[:4]
    else:
        source = [
            PulseTheme(
                theme="Fee clarity",
                summary="Customers need reassurance before acting on fund costs.",
                count=8,
            ),
            PulseTheme(
                theme="Fund comparison",
                summary="Customers want advisor help choosing between similar options.",
                count=6,
            ),
            PulseTheme(
                theme="Trust and next steps",
                summary="Users need confidence on the right action after reading insights.",
                count=5,
            ),
        ]
    rows: list[dict[str, object]] = []
    for theme in source:
        percent = max(12, round((theme.count / total) * 100))
        rows.append(
            {
                "category": theme.theme,
                "count": theme.count,
                "percent": percent,
                "explanation": theme.summary,
            }
        )
    return rows


def _format_created_ist(created_at: datetime | None) -> str:
    if created_at is None:
        return "—"
    utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    ist = utc.astimezone(ZoneInfo("Asia/Kolkata"))
    return ist.strftime("%d %b %Y · %H:%M IST")


def _stars(rating: int) -> str:
    r = max(1, min(5, rating))
    asterisks = "*" * r
    return (
        f'<span style="color:#F59E0B;font-weight:700;font-size:12px;line-height:1;">'
        f"{_e(asterisks)}</span>"
    )


def build_pulse_plain(pulse: WeeklyPulse | None) -> tuple[str, str]:
    if pulse is None:
        subject = "Weekly Pulse — not available yet"
        body = (
            "Hello,\n\n"
            "Weekly Pulse is not available yet. Generate a pulse in the dashboard to receive "
            "the full briefing by email.\n\n"
            "— Groww Product Operations Ecosystem\n"
            "Scheduling: Every Monday at 10:00 AM IST\n"
        )
        return subject, body

    themes = (
        "\n".join([f"- {_e(t.theme)}: {_e(t.summary)} (count={t.count})" for t in pulse.themes[:8]])
        or "- (none)"
    )
    actions = (
        "\n".join([f"- {_e(a)}" for a in pulse.recommended_actions[:8]]) or "- (none)"
    )
    subject = f"Weekly Pulse — {pulse.pulse_id}"
    body = (
        "Hello,\n\n"
        "Here is your Weekly Pulse from the Product Operations Ecosystem dashboard.\n\n"
        f"Pulse ID: {pulse.pulse_id}\n"
        f"Refreshed (IST): {_format_created_ist(pulse.created_at)}\n"
        f"Degraded mode: {pulse.degraded}\n\n"
        f"Narrative:\n{_e(pulse.narrative)}\n\n"
        f"Themes:\n{themes}\n\n"
        f"Recommended actions:\n{actions}\n\n"
        "Future sends: Every Monday at 10:00 AM IST\n\n"
        "— Groww Product Operations Ecosystem\n"
    )
    return subject, body


def build_pulse_html(pulse: WeeklyPulse | None) -> str:
    c = _COLORS
    if pulse is None:
        return (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0;padding:24px 12px;background:{c["bg"]};font-family:Inter,Segoe UI,sans-serif;">'
            f'<tr><td align="center">'
            f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" '
            f'style="max-width:640px;background:{c["surface"]};border-radius:24px;border:1px solid {c["border"]};'
            f'box-shadow:0 12px 30px rgba(31,36,48,0.06);overflow:hidden;">'
            f'<tr><td style="padding:28px 28px 8px 28px;">'
            f'<p style="margin:0 0 8px 0;font-size:11px;font-weight:700;letter-spacing:0.12em;'
            f'text-transform:uppercase;color:{c["faint"]};">Product Operations</p>'
            f'<h1 style="margin:0;font-size:28px;font-weight:600;color:{c["text"]};letter-spacing:-0.02em;">'
            f"Weekly Pulse</h1>"
            f'<p style="margin:12px 0 0 0;font-size:14px;line-height:1.6;color:{c["muted"]};">'
            f"No pulse is available yet. Open the Product tab and generate a pulse to receive "
            f"this briefing by email.</p>"
            f"</td></tr>"
            f'<tr><td style="padding:8px 28px 28px 28px;">'
            f'<p style="margin:0;font-size:12px;color:{c["faint"]};">'
            f"Every Monday · 10:00 AM IST · Groww Product Operations Ecosystem</p>"
            f"</td></tr></table></td></tr></table>"
        )

    top_theme = pulse.themes[0].theme if pulse.themes else "Awaiting signal"
    max_theme_count = max((t.count for t in pulse.themes), default=1)
    booking = _infer_booking_reasons(pulse.themes)
    inferred_demand = sum(int(r["count"]) for r in booking)

    def metric_card(
        label: str,
        value: str,
        detail: str,
        accent: bool = False,
    ) -> str:
        bg = (
            f"linear-gradient(135deg,{c['accentSoft']} 0%,{c['surface']} 100%)"
            if accent
            else c["surface"]
        )
        border = f"1px solid {c['border']}" if not accent else f"1px solid #EDE9FE"
        return (
            f'<td style="width:50%;padding:6px;vertical-align:top;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{bg};border-radius:16px;border:{border};'
            f'box-shadow:0 12px 30px rgba(31,36,48,0.06);">'
            f'<tr><td style="padding:16px 18px;">'
            f'<p style="margin:0;font-size:10px;font-weight:700;letter-spacing:0.14em;'
            f'text-transform:uppercase;color:{c["faint"]};">{_e(label)}</p>'
            f'<p style="margin:8px 0 0 0;font-size:22px;font-weight:600;color:{c["text"]};'
            f'line-height:1.2;">{_e(value)}</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};line-height:1.5;">'
            f"{_e(detail)}</p>"
            f"</td></tr></table></td>"
        )

    hero_degraded = ""
    if pulse.degraded:
        degraded_copy = (
            f"Analysis is in degraded mode. Only {pulse.metrics.reviews_considered} reviews "
            f"were available in this run."
            if pulse.metrics.reviews_considered < 150
            else "Analysis is in degraded mode. The pulse uses the available review set with "
            "fallback analysis where needed."
        )
        hero_degraded = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-top:16px;border-radius:16px;border:1px solid {c["amberBorder"]};'
            f'background:{c["amberBg"]};">'
            f'<tr><td style="padding:14px 16px;font-size:13px;line-height:1.55;color:{c["amberFg"]};">'
            f'{_e(degraded_copy)}<br/><span style="display:block;padding-top:6px;">'
            f"{_e(_readable_degraded_reason(pulse.degraded_reason))}</span>"
            f"</td></tr></table>"
        )

    themes_html_parts: list[str] = []
    for index, theme in enumerate(pulse.themes[:8]):
        intensity = max(8, round((theme.count / max_theme_count) * 100))
        code = _theme_code(theme.theme, index)
        themes_html_parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:12px;border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};box-shadow:0 2px 8px rgba(31,36,48,0.04);">'
            f'<tr><td style="padding:14px 16px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="vertical-align:top;">'
            f'<p style="margin:0;font-size:15px;font-weight:600;color:{c["text"]};">'
            f"{_e(theme.theme)}</p>"
            f'<p style="margin:4px 0 0 0;font-family:ui-monospace,Menlo,monospace;font-size:11px;'
            f'font-weight:700;color:{c["accent"]};">{_e(code)}</p>'
            f'</td><td align="right" style="vertical-align:top;">'
            f'<span style="display:inline-block;border-radius:999px;background:{c["surfaceSoft"]};'
            f'padding:6px 10px;font-size:11px;font-weight:700;color:{c["muted"]};">'
            f'{theme.count} mentions</span>'
            f'</td></tr></table>'
            f'<p style="margin:10px 0 0 0;font-size:13px;line-height:1.55;color:{c["muted"]};">'
            f"{_e(theme.summary)}</p>"
            f'<p style="margin:10px 0 0 0;font-size:11px;font-weight:700;color:{c["text"]};">'
            f"Why this matters</p>"
            f'<p style="margin:4px 0 0 0;font-size:13px;line-height:1.55;color:{c["muted"]};">'
            f"This signal can affect trust, completion, or advisor demand if the same question "
            f"repeats across channels.</p>"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-top:10px;"><tr>'
            f'<td style="height:8px;border-radius:999px;background:{c["surfaceSoft"]};overflow:hidden;">'
            f'<div style="height:8px;width:{intensity}%;border-radius:999px;'
            f'background:{c["accent"]};"></div>'
            f"</td></tr></table>"
            f"</td></tr></table>"
        )

    if not themes_html_parts:
        themes_html_parts.append(
            f'<p style="margin:0;padding:18px;border-radius:16px;border:1px dashed {c["border"]};'
            f'background:{c["surface"]};font-size:13px;color:{c["muted"]};">'
            f"Theme cards appear after a pulse is generated from review inputs.</p>"
        )

    booking_html_parts: list[str] = []
    for row in booking:
        pct = int(row["percent"])
        booking_html_parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:12px;border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};">'
            f'<tr><td style="padding:14px 16px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td><p style="margin:0;font-size:15px;font-weight:600;color:{c["text"]};">'
            f"{_e(str(row['category']))}</p>"
            f'<p style="margin:4px 0 0 0;font-size:10px;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{c["faint"]};">Inferred advisor demand</p>'
            f'</td><td align="right" valign="top">'
            f'<span style="font-size:20px;font-weight:600;color:{c["text"]};">'
            f'{int(row["count"])}</span>'
            f"</td></tr></table>"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-top:10px;"><tr>'
            f'<td style="height:8px;border-radius:999px;background:{c["surfaceSoft"]};overflow:hidden;">'
            f'<div style="height:8px;width:{pct}%;border-radius:999px;background:{c["accentBlue"]};">'
            f"</div></td></tr></table>"
            f'<p style="margin:10px 0 0 0;font-size:13px;line-height:1.55;color:{c["muted"]};">'
            f"{_e(str(row['explanation']))}</p>"
            f'<p style="margin:8px 0 0 0;font-size:11px;font-weight:700;color:{c["text"]};">'
            f"Why it matters</p>"
            f'<p style="margin:4px 0 0 0;font-size:12px;line-height:1.55;color:{c["muted"]};">'
            f"Customers in this category are likely asking for confidence, not just information.</p>"
            f"</td></tr></table>"
        )

    quotes_html: list[str] = []
    n_themes = max(len(pulse.themes), 1)
    for index, quote in enumerate(pulse.quotes[:6]):
        theme_name = pulse.themes[index % n_themes].theme if pulse.themes else None
        sentiment = "Friction" if quote.rating <= 2 else ("Positive" if quote.rating >= 4 else "Mixed")
        voc = f"VOC-{index + 1:02d}"
        chip_theme = ""
        if theme_name:
            chip_theme = (
                f'<span style="display:inline-block;margin:4px 4px 0 0;padding:6px 10px;'
                f'border-radius:999px;border:1px solid {c["border"]};background:{c["surface"]};'
                f'font-size:11px;font-weight:600;color:{c["muted"]};">{_e(theme_name)}</span>'
            )
        quotes_html.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:10px;border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};">'
            f'<tr><td style="padding:14px 16px;">'
            f'<table role="presentation" width="100%"><tr>'
            f'<td><span style="font-family:ui-monospace,Menlo,monospace;font-size:11px;'
            f'font-weight:700;color:{c["accent"]};">{_e(voc)}</span></td>'
            f'<td align="right">{_stars(quote.rating)}</td>'
            f"</tr></table>"
            f'<p style="margin:10px 0 0 0;font-size:13px;line-height:1.6;color:{c["text"]};">'
            f"{_e(quote.quote)}</p>"
            f'<p style="margin:10px 0 0 0;">'
            f'<span style="display:inline-block;margin:4px 4px 0 0;padding:6px 10px;'
            f'border-radius:999px;border:1px solid {c["border"]};background:{c["surface"]};'
            f'font-size:11px;font-weight:600;color:{c["muted"]};">Review {_e(quote.review_id)}</span>'
            f'<span style="display:inline-block;margin:4px 4px 0 0;padding:6px 10px;'
            f'border-radius:999px;border:1px solid {c["border"]};background:{c["surface"]};'
            f'font-size:11px;font-weight:600;color:{c["muted"]};">{_e(sentiment)}</span>'
            f"{chip_theme}</p>"
            f"</td></tr></table>"
        )

    if not quotes_html:
        quotes_html.append(
            f'<p style="margin:0;padding:18px;border-radius:16px;border:1px dashed {c["border"]};'
            f'color:{c["muted"]};font-size:13px;">'
            f"Customer quotes appear here after the pulse has review context.</p>"
        )

    actions_html: list[str] = []
    for index, action in enumerate(pulse.recommended_actions[:8]):
        owner = OWNER_POOL[index % len(OWNER_POOL)]
        pri = min(index + 1, 3)
        actions_html.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:10px;border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};">'
            f'<tr><td style="padding:14px 16px;">'
            f'<p style="margin:0;">'
            f'<span style="display:inline-block;margin:0 6px 0 0;padding:6px 10px;border-radius:999px;'
            f'background:{c["accentSoft"]};font-size:11px;font-weight:700;color:{c["accent"]};">'
            f"P{pri}</span>"
            f'<span style="display:inline-block;padding:6px 10px;border-radius:999px;'
            f'background:{c["surfaceSoft"]};font-size:11px;font-weight:700;color:{c["muted"]};">'
            f"Owner: {_e(owner)}</span></p>"
            f'<h4 style="margin:12px 0 0 0;font-size:14px;font-weight:600;color:{c["text"]};">'
            f"{_e(_action_title(action))}</h4>"
            f'<p style="margin:8px 0 0 0;font-size:13px;line-height:1.55;color:{c["muted"]};">'
            f"{_e(_action_body(action))}</p>"
            f'<p style="margin:10px 0 0 0;font-size:11px;font-weight:700;color:{c["text"]};">'
            f"Why this matters</p>"
            f'<p style="margin:4px 0 0 0;font-size:13px;line-height:1.55;color:{c["muted"]};">'
            f"{_e(_action_why(action))}</p>"
            f"</td></tr></table>"
        )

    if not actions_html:
        actions_html.append(
            f'<p style="margin:0;padding:18px;border-radius:16px;border:1px dashed {c["border"]};'
            f'color:{c["muted"]};font-size:13px;">'
            f"Action cards appear after the pulse is generated.</p>"
        )

    narrative_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin-top:8px;border-radius:16px;background:{c["surfaceSoft"]};">'
        f'<tr><td style="padding:18px 20px;font-size:15px;line-height:1.65;color:{c["text"]};">'
        f"{_e(pulse.narrative)}"
        f"</td></tr></table>"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">'
        f"<tr>"
        f'<td width="33%" style="vertical-align:top;padding:4px;">'
        f'<table width="100%" style="border-radius:12px;background:{c["surface"]};"><tr>'
        f'<td style="padding:12px;"><p style="margin:0;font-size:10px;font-weight:700;'
        f'letter-spacing:0.14em;text-transform:uppercase;color:{c["faint"]};">Primary signal</p>'
        f'<p style="margin:8px 0 0 0;font-size:13px;font-weight:600;color:{c["text"]};">'
        f'{_e(top_theme)}</p></td></tr></table></td>'
        f'<td width="33%" style="vertical-align:top;padding:4px;">'
        f'<table width="100%" style="border-radius:12px;background:{c["surface"]};"><tr>'
        f'<td style="padding:12px;"><p style="margin:0;font-size:10px;font-weight:700;'
        f'letter-spacing:0.14em;text-transform:uppercase;color:{c["faint"]};">Evidence</p>'
        f'<p style="margin:8px 0 0 0;font-size:13px;font-weight:600;color:{c["text"]};">'
        f'{len(pulse.quotes)} customer quotes</p></td></tr></table></td>'
        f'<td width="33%" style="vertical-align:top;padding:4px;">'
        f'<table width="100%" style="border-radius:12px;background:{c["surface"]};"><tr>'
        f'<td style="padding:12px;"><p style="margin:0;font-size:10px;font-weight:700;'
        f'letter-spacing:0.14em;text-transform:uppercase;color:{c["faint"]};">PM focus</p>'
        f'<p style="margin:8px 0 0 0;font-size:13px;font-weight:600;color:{c["text"]};">'
        f'Reduce repeat advisor escalations</p></td></tr></table></td>'
        f"</tr></table>"
    )

    return "".join(
        [
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0;padding:20px 10px;background:{c["bg"]};font-family:Inter,Segoe UI,'
            f'system-ui,sans-serif;color:{c["text"]};">',
            '<tr><td align="center">',
            f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" '
            f'style="max-width:640px;width:100%;">',
            # Hero
            "<tr><td "
            f'style="padding:24px 22px;border-radius:28px;border:1px solid rgba(255,255,255,0.8);'
            f'background:linear-gradient(135deg,rgba(249,168,212,0.22) 0%,transparent 45%),'
            f'linear-gradient(135deg,rgba(96,165,250,0.18) 50%,transparent 70%),'
            f'linear-gradient(180deg,rgba(124,58,237,0.08) 100%,transparent),'
            f'rgba(255,255,255,0.92);box-shadow:0 18px 50px rgba(31,36,48,0.08);">',
            f'<table role="presentation" width="100%"><tr>'
            f'<td style="vertical-align:top;">'
            f'<p style="margin:0 0 8px 0;">'
            f'<span style="display:inline-block;padding:6px 10px;border-radius:999px;'
            f'background:{"#FFFBEB" if pulse.degraded else "#ECFDF5"};color:{"#B45309" if pulse.degraded else "#047857"};'
            f'font-size:11px;font-weight:700;">Latest pulse ready</span> '
            f'<span style="display:inline-block;margin-left:6px;padding:6px 10px;border-radius:999px;'
            f'border:1px solid {c["border"]};background:{c["surface"]};font-size:11px;'
            f'font-weight:600;color:{c["muted"]};">Every Monday · 10:00 AM IST</span></p>'
            f'<h1 style="margin:12px 0 0 0;font-size:32px;font-weight:600;letter-spacing:-0.02em;'
            f'color:{c["text"]};">Weekly Pulse</h1>'
            f'<p style="margin:10px 0 0 0;font-size:14px;line-height:1.55;color:{c["muted"]};">'
            f"Insights from customer questions, reviews, and advisor demand.</p>"
            f'<p style="margin:10px 0 0 0;font-size:11px;font-weight:700;color:{c["faint"]};">'
            f"PULSE {_e(pulse.pulse_id)} — refreshed {_e(_format_created_ist(pulse.created_at))}</p>"
            f'{hero_degraded}'
            f"</td>"
            f'<td style="vertical-align:top;width:210px;padding-left:14px;">'
            f'<table role="presentation" width="100%" style="border-radius:16px;'
            f'border:1px solid {c["border"]};background:rgba(255,255,255,0.92);box-shadow:'
            f'0 12px 30px rgba(31,36,48,0.06);"><tr><td style="padding:14px 16px;">'
            f'<p style="margin:0;font-size:11px;font-weight:700;color:{c["faint"]};">'
            f"Next scheduled send</p>"
            f'<p style="margin:6px 0 0 0;font-size:18px;font-weight:600;color:{c["text"]};">'
            f"Monday, 10:00 AM IST</p>"
            f'<p style="margin:6px 0 0 0;font-size:11px;line-height:1.45;color:{c["muted"]};">'
            f"Same briefing as the Product tab dashboard.</p>"
            f"</td></tr></table></td></tr></table>",
            "</td></tr>",
            # Metric row
            "<tr><td style=\"padding-top:14px;\">",
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>',
            metric_card(
                "Reviews analyzed",
                str(pulse.metrics.reviews_considered),
                "Cleaned review inputs",
            ),
            metric_card(
                "Average rating",
                f"{pulse.metrics.average_rating:.2f}",
                "Across reviewed inputs",
            ),
            "</tr><tr>",
            metric_card(
                "Top issue theme",
                top_theme,
                "Highest mention cluster",
                accent=True,
            ),
            metric_card(
                "Advisor booking intent",
                str(inferred_demand),
                "Inferred from current themes",
            ),
            "</tr></table>",
            "</td></tr>",
            # Narrative section
            f'<tr><td style="padding-top:14px;">'
            f'<table role="presentation" width="100%" style="border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};box-shadow:0 12px 30px rgba(31,36,48,0.06);">'
            f'<tr><td style="padding:18px 20px;">'
            f'<p style="margin:0;font-size:17px;font-weight:600;color:{c["text"]};">'
            f"This week in summary</p>"
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};">'
            f"Executive narrative for PM and operations review.</p>"
            f"{narrative_block}"
            f"</td></tr></table></td></tr>",
            # Themes + booking grid
            f'<tr><td style="padding-top:14px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr valign="top">'
            f'<td style="width:58%;padding-right:8px;">'
            f'<table role="presentation" width="100%" style="border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};box-shadow:0 12px 30px rgba(31,36,48,0.06);">'
            f'<tr><td style="padding:18px 20px;">'
            f'<p style="margin:0;font-size:17px;font-weight:600;">Pulse themes</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};">'
            f"Issue clusters with PM-ready context and intensity.</p>"
            f'<div style="margin-top:14px;">{"".join(themes_html_parts)}</div>'
            f"</td></tr></table></td>",
            f'<td style="width:42%;padding-left:8px;">'
            f'<table role="presentation" width="100%" style="border-radius:16px;border:1px solid {c["border"]};'
            f'background:{c["surface"]};">'
            f'<tr><td style="padding:18px 20px;">'
            f'<p style="margin:0;font-size:17px;font-weight:600;">Why customers book advisors</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};">'
            f"Inferred from pulse themes until direct booking analytics are available.</p>"
            f'<div style="margin-top:14px;">{"".join(booking_html_parts)}</div>'
            f"</td></tr></table></td>"
            f"</tr></table></td></tr>",
            # VOC + Actions
            f'<tr><td style="padding-top:14px;">'
            f'<table role="presentation" width="100%"><tr valign="top">'
            f'<td style="width:50%;padding-right:8px;">'
            f'<table width="100%" style="border-radius:16px;border:1px solid {c["border"]};background:{c["surface"]};">'
            f'<tr><td style="padding:18px 18px;">'
            f'<p style="margin:0;font-size:17px;font-weight:600;">Voice of customer</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};">'
            f"Representative quotes from the current pulse.</p>"
            f'<div style="margin-top:14px;">{"".join(quotes_html)}</div>'
            f"</td></tr></table></td>"
            f'<td style="width:50%;padding-left:8px;">'
            f'<table width="100%" style="border-radius:16px;border:1px solid {c["border"]};background:{c["surface"]};">'
            f'<tr><td style="padding:18px 18px;">'
            f'<p style="margin:0;font-size:17px;font-weight:600;">Recommended actions</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:{c["muted"]};">'
            f"Prioritized follow-ups for PM, Ops, Support, and advisor teams.</p>"
            f'<div style="margin-top:14px;">{"".join(actions_html)}</div>'
            f"</td></tr></table></td>"
            f"</tr></table></td></tr>",
            f'<tr><td align="center" style="padding:18px 4px 8px 4px;font-size:11px;line-height:1.5;'
            f'color:{c["faint"]};">Groww Product Operations Ecosystem · Weekly Pulse email</td></tr>',
            "</table></td></tr></table>",
        ]
    )


def build_pulse_email_parts(pulse: WeeklyPulse | None) -> tuple[str, str, str]:
    """Return (subject, text_plain, text_html)."""
    subject, plain = build_pulse_plain(pulse)
    html_doc = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/></head>'
        f"<body style=\"margin:0;background:{_COLORS['bg']};\">"
        f"{build_pulse_html(pulse)}"
        "</body></html>"
    )
    return subject, plain, html_doc
