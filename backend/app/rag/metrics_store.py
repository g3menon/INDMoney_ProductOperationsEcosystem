"""Phase 4: In-memory structured MF metrics store.

Loaded at backend startup from backend/app/rag/index/mf_metrics.json (built by
scripts/rebuild_index.py).  If the file is absent the store is empty and the
system falls back to RAG-only answers — identical to how RAGIndex degrades.

Matching logic uses normalized token-overlap scoring against fund name + AMC +
category.  Deterministic and fast (Rules L7); no fuzzy-string dependency.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.schemas.rag import MFFundMetrics

logger = logging.getLogger(__name__)

_DEFAULT_METRICS_PATH = str(
    Path(__file__).parent / "index" / "mf_metrics.json"
)

_TOKENIZE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKENIZE.findall(text.lower()))


# Common English stop-words that should not inflate match scores.
_STOP_TOKENS: frozenset[str] = frozenset(
    [
        "fund", "direct", "regular", "growth", "idcw", "plan", "the", "and",
        "of", "in", "for", "a", "an", "is", "are", "to", "by", "on",
    ]
)


def _meaningful_tokens(text: str) -> set[str]:
    return _tokens(text) - _STOP_TOKENS


class MFMetricsStore:
    """In-memory store of structured MFFundMetrics objects."""

    def __init__(self, metrics: list[MFFundMetrics]) -> None:
        self._by_doc_id: dict[str, MFFundMetrics] = {m.doc_id: m for m in metrics}
        self._by_url: dict[str, MFFundMetrics] = {m.source_url: m for m in metrics}
        self._all: list[MFFundMetrics] = list(metrics)
        logger.info(
            "mf_metrics_store_loaded", extra={"count": len(metrics)}
        )

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str) -> "MFMetricsStore":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"MF metrics index not found: {path}")
        raw = json.loads(p.read_text(encoding="utf-8"))
        metrics = [MFFundMetrics.model_validate(r) for r in raw]
        return cls(metrics)

    @classmethod
    def load_default(cls) -> "MFMetricsStore | None":
        try:
            return cls.load(_DEFAULT_METRICS_PATH)
        except FileNotFoundError:
            logger.warning(
                "mf_metrics_index_missing",
                extra={
                    "path": _DEFAULT_METRICS_PATH,
                    "hint": "run scripts/rebuild_index.py to generate mf_metrics.json",
                },
            )
            return None
        except Exception as exc:
            logger.error(
                "mf_metrics_store_load_error", extra={"error": str(exc)}
            )
            return None

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def lookup_by_doc_id(self, doc_id: str) -> MFFundMetrics | None:
        return self._by_doc_id.get(doc_id)

    def lookup_by_url(self, url: str) -> MFFundMetrics | None:
        return self._by_url.get(url)

    def find_closest_match(self, query: str) -> MFFundMetrics | None:
        """Return the best-matching fund for a free-text query.

        Scores each fund by meaningful-token overlap between the query and
        (fund_name + amc + category).  Returns None when no fund scores above
        a minimum threshold.
        """
        query_tokens = _meaningful_tokens(query)
        if not query_tokens:
            return None

        best: MFFundMetrics | None = None
        best_score = 0.0

        for m in self._all:
            fund_tokens = (
                _meaningful_tokens(m.fund_name or "")
                | _meaningful_tokens(m.amc or "")
                | _meaningful_tokens(m.category or "")
            )
            if not fund_tokens:
                continue
            overlap = len(query_tokens & fund_tokens)
            # Jaccard-style but biased toward query coverage.
            score = overlap / max(len(query_tokens), 1)
            if score > best_score:
                best_score = score
                best = m

        # Require at least one fund-specific token to match.
        min_threshold = min(0.12, 1.0 / max(len(query_tokens), 1))
        if best_score < min_threshold:
            return None

        logger.debug(
            "mf_metrics_match",
            extra={
                "query": query[:60],
                "matched": best.doc_id if best else None,
                "score": round(best_score, 3),
            },
        )
        return best

    def all(self) -> list[MFFundMetrics]:
        return list(self._all)


# ---------------------------------------------------------------------------
# Module-level singleton (loaded at startup in main.py)
# ---------------------------------------------------------------------------

_store: MFMetricsStore | None = None


def get_metrics_store() -> MFMetricsStore | None:
    return _store


def set_metrics_store(store: MFMetricsStore | None) -> None:
    global _store
    _store = store


async def load_metrics_store_from_default() -> None:
    """Called at startup (main.py lifespan).  Safe even if index file is absent."""
    s = MFMetricsStore.load_default()
    set_metrics_store(s)
