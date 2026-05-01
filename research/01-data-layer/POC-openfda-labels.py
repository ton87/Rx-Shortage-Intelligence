"""
POC: openFDA Drug Label fetch + section extraction.

Run: python research/01-data-layer/POC-openfda-labels.py

Demonstrates:
- Search by RxCUI or generic_name
- Extract only the 7 sections relevant to shortage briefings
- Estimate token count for RAG chunking
"""

import httpx
import json

BASE = "https://api.fda.gov/drug/label.json"

KEEP_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "boxed_warning",
    "drug_interactions",
    "clinical_pharmacology",
]


def fetch_label_by_rxcui(rxcui: str) -> dict | None:
    """Return first matching label record or None."""
    params = {"search": f"openfda.rxcui:{rxcui}", "limit": 1}
    resp = httpx.get(BASE, params=params, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def fetch_label_by_name(generic_name: str) -> dict | None:
    """Fallback: search by generic_name when RxCUI lookup fails."""
    params = {"search": f"openfda.generic_name:{generic_name}", "limit": 1}
    resp = httpx.get(BASE, params=params, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def extract_relevant_sections(label: dict) -> dict:
    """Return dict keyed by section name with concatenated text."""
    out = {}
    for section in KEEP_SECTIONS:
        val = label.get(section)
        if val:
            # openFDA returns lists of strings for many fields
            text = "\n".join(val) if isinstance(val, list) else str(val)
            out[section] = text
    return out


def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 chars in English."""
    return len(text) // 4


if __name__ == "__main__":
    # Cisplatin RxCUI
    label = fetch_label_by_rxcui("2555")
    if not label:
        print("No label by RxCUI, trying name fallback...")
        label = fetch_label_by_name("cisplatin")

    if not label:
        print("No label found.")
        exit(1)

    sections = extract_relevant_sections(label)
    print(f"Found {len(sections)} relevant sections.\n")
    for name, text in sections.items():
        tokens = estimate_tokens(text)
        preview = text[:200].replace("\n", " ")
        print(f"--- {name} (~{tokens} tokens) ---")
        print(f"{preview}...\n")

    total_tokens = sum(estimate_tokens(t) for t in sections.values())
    print(f"\nTotal relevant tokens: ~{total_tokens}")
    print(f"Full record JSON size: {len(json.dumps(label))} bytes")
