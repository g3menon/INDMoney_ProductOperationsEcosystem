"""Phase 2 chunking / segmentation for Weekly Pulse preprocessing.

This is *not* Phase 4 RAG chunking. It only segments overly long review text so
theme/pulse prompts remain bounded (`Docs/Rules.md` R3).
"""

from __future__ import annotations

import re


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def segment_review_text(text: str, max_chars: int = 800) -> list[str]:
    """
    - If short: one review = one segment.
    - If long: split by sentences, then pack into <= max_chars segments.
    """
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]

    parts = _SENTENCE_SPLIT.split(t)
    segments: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not buf:
            buf = p
            continue
        if len(buf) + 1 + len(p) <= max_chars:
            buf = f"{buf} {p}"
        else:
            segments.append(buf)
            buf = p
    if buf:
        segments.append(buf)

    # Hard fallback: if still too long (no punctuation), chunk by characters.
    final: list[str] = []
    for s in segments:
        if len(s) <= max_chars:
            final.append(s)
        else:
            for i in range(0, len(s), max_chars):
                final.append(s[i : i + max_chars].strip())
    return [x for x in final if x]

