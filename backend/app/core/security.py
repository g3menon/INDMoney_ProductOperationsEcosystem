"""Security helpers (tokens, redaction). Phase 1: redaction utilities only."""

from __future__ import annotations

import re

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.I),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"service_role\s+\S+", re.I),
)


def redact_secrets(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out
