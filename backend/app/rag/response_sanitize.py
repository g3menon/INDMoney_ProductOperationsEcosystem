"""Post-process assistant text to remove legacy or model-invented engineering copy."""

from __future__ import annotations

import re

from app.rag.public_messages import NAV_UNAVAILABLE_FOR_USER

# Old / hallucinated NAV lines (never show scraping or Playwright to customers).
_NAV_INTERNAL_HINTS = re.compile(
    r"(not yet available|playwright|mf_extractor|js rendering|javascript rendering|live data requires)",
    re.IGNORECASE,
)


def sanitize_mf_assistant_text(text: str) -> str:
    """Normalize NAV lines that leak implementation details or legacy wording."""
    if not text:
        return text
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("nav:") or lower.startswith("**nav:"):
            rest = stripped
            if _NAV_INTERNAL_HINTS.search(rest):
                # Keep markdown emphasis on the label only when the line used **Fund** style elsewhere
                if stripped.startswith("**NAV:") or stripped.startswith("**nav:"):
                    lines.append(f"**NAV:** {NAV_UNAVAILABLE_FOR_USER}")
                else:
                    lines.append(f"NAV: {NAV_UNAVAILABLE_FOR_USER}")
                continue
        lines.append(line)
    return "\n".join(lines)
