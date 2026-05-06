"""Canonical MF corpus must stay aligned with Deliverables/Resources.md."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "scripts" / "sources_manifest.json"
_MF_METRICS_PATH = _REPO_ROOT / "backend" / "app" / "rag" / "index" / "mf_metrics.json"

# Mutual fund rows in Deliverables/Resources.md (Motilal + HDFC tables).
_RESOURCES_MF_DOC_IDS: frozenset[str] = frozenset(
    {
        "motilal-midcap-direct",
        "motilal-flexicap-direct",
        "motilal-midcap150-index",
        "hdfc-large-midcap-direct",
        "hdfc-flexicap-direct",
        "hdfc-largecap-direct",
    }
)


def _manifest_mf_sources() -> list[dict]:
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return [r for r in raw if isinstance(r, dict) and r.get("doc_type") == "mutual_fund_page"]


def test_sources_manifest_matches_resources_mutual_fund_set() -> None:
    mf = _manifest_mf_sources()
    ids = {r["doc_id"] for r in mf}
    assert ids == _RESOURCES_MF_DOC_IDS


def test_mf_metrics_index_matches_manifest_mutual_fund_set() -> None:
    mf = _manifest_mf_sources()
    manifest_ids = {r["doc_id"] for r in mf}

    metrics_raw = json.loads(_MF_METRICS_PATH.read_text(encoding="utf-8"))
    index_ids = {r["doc_id"] for r in metrics_raw}

    assert index_ids == manifest_ids
