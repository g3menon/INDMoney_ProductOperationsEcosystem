"""Phase 2 + Phase 4 chunking / segmentation.

Phase 2: segments overly long review text so theme/pulse prompts stay bounded (Rules R3).
Phase 4: semantic paragraph-level chunking of MF/fee web documents for the RAG index
         (Rules R12, P4.8). Chunks retain source metadata end to end.
"""

from __future__ import annotations

import hashlib
import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARA_SPLIT = re.compile(r"\n{2,}")


# ---------------------------------------------------------------------------
# Phase 2: Review text segmentation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase 4: Web document chunking (Rules R12, P4.8)
# ---------------------------------------------------------------------------


def chunk_document(
    doc: "SourceDocument",
    max_chars: int = 700,
) -> list["DocumentChunk"]:
    """Split a SourceDocument into paragraph-level DocumentChunks.

    Strategy (Rules R12):
    1. Split on blank lines (paragraph boundaries) first.
    2. If a paragraph exceeds max_chars, sentence-split and pack.
    3. Each chunk retains source_url, doc_type, title, last_checked for citations.
    """
    from app.schemas.rag import DocumentChunk, SourceDocument  # local to avoid circular

    text = (doc.content or "").strip()
    if not text:
        return []

    # Step 1: paragraph split.
    raw_paras = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]

    # Step 2: break oversized paragraphs at sentence boundaries.
    passages: list[str] = []
    for para in raw_paras:
        if len(para) <= max_chars:
            passages.append(para)
        else:
            sentences = _SENTENCE_SPLIT.split(para)
            buf = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if not buf:
                    buf = sent
                elif len(buf) + 1 + len(sent) <= max_chars:
                    buf = f"{buf} {sent}"
                else:
                    passages.append(buf)
                    buf = sent
            if buf:
                passages.append(buf)

    # Step 3: build typed DocumentChunk objects.
    chunks: list[DocumentChunk] = []
    for idx, passage in enumerate(passages):
        if len(passage) < 30:
            continue
        chunk_id = _stable_chunk_id(doc.doc_id, idx, passage)
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                source_url=doc.url,
                title=doc.title,
                doc_type=doc.doc_type,
                last_checked=doc.last_checked,
                content=passage,
                chunk_index=idx,
            )
        )

    return chunks


def _stable_chunk_id(doc_id: str, idx: int, content: str) -> str:
    """Deterministic chunk ID from doc_id + index + content hash prefix (Rules D8)."""
    h = hashlib.sha256(f"{doc_id}:{idx}:{content[:64]}".encode()).hexdigest()[:12]
    return f"CHK-{h.upper()}"
