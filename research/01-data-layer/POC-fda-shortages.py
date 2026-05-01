"""
POC: live fetch of FDA Drug Shortage feed.

Run: python research/01-data-layer/POC-fda-shortages.py

Demonstrates:
- No auth required
- Top-level shape: meta + results[]
- Each result has openfda.rxcui, generic_name, status, reason
- Both 'current' and 'resolved' included via status filter
"""

import httpx
import json

BASE = "https://api.fda.gov/drug/shortages.json"


def fetch_current_shortages(limit: int = 10) -> dict:
    """Fetch top N current shortages."""
    params = {
        "search": "status:Current",  # actual FDA value; see QUESTIONS-FOR-ANTON.md Q1 for TBD handling
        "limit": limit,
    }
    resp = httpx.get(BASE, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_by_rxcui(rxcui: str) -> dict:
    """Fetch shortage record(s) for a specific RxCUI."""
    params = {
        "search": f"openfda.rxcui:{rxcui}",
        "limit": 5,
    }
    resp = httpx.get(BASE, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def summarize(record: dict) -> str:
    """One-line summary of a shortage record."""
    name = record.get("generic_name", "UNKNOWN")
    status = record.get("status", "?")
    reason = record.get("shortage_reason", "n/a")
    rxcui = (record.get("openfda") or {}).get("rxcui", ["n/a"])
    return f"{name} | {status} | reason={reason[:60]} | rxcui={rxcui[0] if rxcui else 'n/a'}"


if __name__ == "__main__":
    print("=== Top 10 current FDA drug shortages ===\n")
    data = fetch_current_shortages(10)
    print(f"Total matching: {data['meta']['results']['total']}")
    print(f"Returned:       {len(data['results'])}\n")

    for i, rec in enumerate(data["results"], 1):
        print(f"{i:2d}. {summarize(rec)}")

    print("\n=== Sample full record (first result) ===\n")
    print(json.dumps(data["results"][0], indent=2)[:1500])
    print("...(truncated)")
