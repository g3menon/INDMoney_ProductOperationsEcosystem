"""
Phase 2 helper: create a pulse via API call (requires backend running).

Usage:
  python scripts/seed_dev_data.py --api http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", type=str, default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.api.rstrip("/")
    r = httpx.post(f"{base}/api/v1/pulse/generate", json={"use_fixture": True, "lookback_weeks": 8}, timeout=30.0)
    r.raise_for_status()
    print(r.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

