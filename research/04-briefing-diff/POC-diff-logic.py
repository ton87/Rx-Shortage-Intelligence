"""
POC: snapshot diff between today's FDA feed and yesterday_snapshot.json.

Run: python research/04-briefing-diff/POC-diff-logic.py

Demonstrates:
- Index by rxcui
- Set ops for new/resolved
- Status comparison for escalated/improved
- Filter to formulary subset
"""

import httpx
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FORMULARY_PATH = ROOT / "data" / "synthetic_formulary.json"
YESTERDAY_PATH = ROOT / "data" / "yesterday_snapshot.json"

STATUS_RANK = {
    "Resolved": 0,
    "Available with limitations": 1,  # legacy/synthetic — not returned by current FDA API
    "Current": 2,                     # active shortage
    "To Be Discontinued": 3,          # being phased out — see QUESTIONS-FOR-ANTON.md Q1
    "Discontinued": 3,                # legacy alias
}


def fetch_today() -> list[dict]:
    resp = httpx.get(
        "https://api.fda.gov/drug/shortages.json",
        params={"limit": 60},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _extract_rxcuis(record: dict) -> list[str]:
    """Extract RxCUI list from either raw FDA shape (openfda.rxcui) or MCP-trimmed shape (top-level rxcui).

    FDA returns list per record (1 generic = many products = many RxCUIs). See QUESTIONS-FOR-ANTON.md Q2.
    """
    raw = (record.get("openfda") or {}).get("rxcui") or record.get("rxcui") or []
    if isinstance(raw, str):
        return [raw]
    return list(raw)


def index_by_rxcui(records: list[dict]) -> dict[str, dict]:
    """Index by EVERY rxcui in the list (1 record → N entries) so any formulary RxCUI can match.

    Last write wins on conflicts; FDA returns one record per generic so collisions are rare.
    """
    out = {}
    for r in records:
        for rxcui in _extract_rxcuis(r):
            out[rxcui] = r
    return out


def is_worse(today_status: str, yest_status: str) -> bool:
    return STATUS_RANK.get(today_status, 1) > STATUS_RANK.get(yest_status, 1)


def compute_diff(today: list[dict], yesterday: list[dict], formulary_rxcuis: set[str]) -> dict:
    t_idx = {k: v for k, v in index_by_rxcui(today).items() if k in formulary_rxcuis}
    y_idx = {k: v for k, v in index_by_rxcui(yesterday).items() if k in formulary_rxcuis}

    t_keys, y_keys = set(t_idx), set(y_idx)
    new_keys = t_keys - y_keys
    resolved_keys = y_keys - t_keys
    overlap = t_keys & y_keys

    escalated, improved, unchanged = [], [], []
    for k in overlap:
        t_status = t_idx[k].get("status", "")
        y_status = y_idx[k].get("status", "")
        if t_status == y_status:
            unchanged.append(t_idx[k])
        elif is_worse(t_status, y_status):
            escalated.append(t_idx[k])
        else:
            improved.append(t_idx[k])

    return {
        "new": [t_idx[k] for k in new_keys],
        "escalated": escalated,
        "improved": improved,
        "resolved": [y_idx[k] for k in resolved_keys],
        "unchanged": unchanged,
    }


if __name__ == "__main__":
    if not FORMULARY_PATH.exists() or not YESTERDAY_PATH.exists():
        print("Run POC-synthetic-formulary.py and POC-yesterday-snapshot.py first.")
        exit(1)

    formulary = json.loads(FORMULARY_PATH.read_text())
    formulary_rxcuis = {d["rxcui"] for d in formulary["drugs"]}
    print(f"Formulary RxCUIs: {len(formulary_rxcuis)}")

    yesterday = json.loads(YESTERDAY_PATH.read_text())["results"]
    print(f"Yesterday records: {len(yesterday)}")

    today = fetch_today()
    print(f"Today records: {len(today)}")

    diff = compute_diff(today, yesterday, formulary_rxcuis)
    print("\n=== Diff buckets (formulary-filtered) ===")
    for bucket, items in diff.items():
        print(f"  {bucket}: {len(items)}")
        for item in items[:3]:
            name = item.get("generic_name", "?")
            status = item.get("status", "?")
            print(f"    - {name} | {status}")
