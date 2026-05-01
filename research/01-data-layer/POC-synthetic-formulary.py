"""
POC: generate synthetic formulary + active orders from live FDA shortage feed.

Run: python research/01-data-layer/POC-synthetic-formulary.py

Why sample FROM the feed: guarantees overlap. No overlap = empty briefing = dead demo.

Outputs:
  data/synthetic_formulary.json
  data/active_orders.json
"""

import httpx
import json
import random
from pathlib import Path
from datetime import datetime, timezone

OUT_DIR = Path(__file__).parent.parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

ROUTES = ["IV", "IM", "PO", "SubQ", "Inhalation", "Topical"]
DEPTS = ["ICU", "Oncology", "ER", "Med-Surg", "Pediatrics", "Surgery", "Ambulatory"]
STATUSES = ["preferred", "non-preferred", "restricted", "non-formulary"]


def fetch_shortage_rxcuis(target_count: int = 30) -> list[dict]:
    """Pull RxCUIs from live FDA shortage feed. Filter to records that have RxCUI."""
    resp = httpx.get(
        "https://api.fda.gov/drug/shortages.json",
        params={"limit": 100},  # over-fetch, filter for rxcui presence
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    drugs = []
    seen_rxcuis = set()
    for rec in results:
        rxcuis = (rec.get("openfda") or {}).get("rxcui") or []
        if not rxcuis:
            continue
        rxcui = rxcuis[0]
        if rxcui in seen_rxcuis:
            continue
        seen_rxcuis.add(rxcui)

        drugs.append({
            "rxcui": rxcui,
            "name": rec.get("generic_name", "Unknown"),
            "source_status": rec.get("status"),
        })
        if len(drugs) >= target_count:
            break

    return drugs


def synthesize_formulary(drugs: list[dict]) -> dict:
    random.seed(42)  # reproducible
    formulary_drugs = []
    for d in drugs:
        formulary_drugs.append({
            "rxcui": d["rxcui"],
            "name": d["name"],
            "formulary_status": random.choice(STATUSES),
            "route_of_administration": random.choice(ROUTES),
            "therapeutic_class": "TBD",  # filled by RxClass at runtime
            "restriction_criteria": random.choice([
                None, "Specialist only", "Oncology only", "ICU only", "Age >18", "Renal-dosed"
            ]),
            "preferred_alternatives": [],
            "last_pt_review_date": "2026-01-15",
        })
    return {
        "customer_id": "memorial-health-450",
        "label": "SYNTHETIC — for v0.1 demo only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "drugs": formulary_drugs,
    }


def synthesize_orders(drugs: list[dict]) -> dict:
    random.seed(43)
    orders = []
    for d in drugs:
        orders.append({
            "rxcui": d["rxcui"],
            "count_last_30_days": random.randint(0, 80),
            "departments": random.sample(DEPTS, k=random.randint(1, 3)),
        })
    return {
        "customer_id": "memorial-health-450",
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "label": "SYNTHETIC",
        "orders": orders,
    }


if __name__ == "__main__":
    print("Fetching live FDA shortage feed for RxCUI sampling...")
    drugs = fetch_shortage_rxcuis(30)
    print(f"Sampled {len(drugs)} drugs with RxCUIs.\n")

    formulary = synthesize_formulary(drugs)
    orders = synthesize_orders(drugs)

    formulary_path = OUT_DIR / "synthetic_formulary.json"
    orders_path = OUT_DIR / "active_orders.json"

    formulary_path.write_text(json.dumps(formulary, indent=2))
    orders_path.write_text(json.dumps(orders, indent=2))

    print(f"Wrote {formulary_path} ({len(formulary['drugs'])} drugs)")
    print(f"Wrote {orders_path} ({len(orders['orders'])} order records)")
    print("\nFirst 3 drugs:")
    for d in formulary["drugs"][:3]:
        print(f"  {d['name']} ({d['rxcui']}) — {d['formulary_status']} / {d['route_of_administration']}")
