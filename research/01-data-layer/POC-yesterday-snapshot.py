"""
POC: generate yesterday_snapshot.json — fictional but real-shaped.

Run: python research/01-data-layer/POC-yesterday-snapshot.py

Strategy: take today's live FDA feed, deliberately edit so diff produces:
  - 2 NEW shortages (in today, not in yesterday)
  - 2 RESOLVED (in yesterday, not in today)
  - 1 RE-OCCURRENCE (yesterday=Resolved, today=Current → triggers rubric Rule C3)
  - 1 MODERATE ESCALATION (yesterday="Available with limitations" synthetic, today=Current)

Output: data/yesterday_snapshot.json

R6 mitigation: only generate if file missing. If file exists, leaves it alone (re-running
this script does NOT overwrite). Delete the file manually to regenerate.

FDA status canonical values: "Current", "To Be Discontinued", "Resolved" (verified 2026-05-01).
"Available with limitations" is a synthetic-only intermediate state used to seed moderate
escalation diff scenarios; not returned by the real FDA API.
"""

import httpx
import json
import random
import sys
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone, timedelta

OUT_DIR = Path(__file__).parent.parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)
OUT_PATH = OUT_DIR / "yesterday_snapshot.json"


def fetch_current_feed(limit: int = 60) -> list[dict]:
    resp = httpx.get(
        "https://api.fda.gov/drug/shortages.json",
        params={"search": "status:Current", "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def make_yesterday(today: list[dict]) -> list[dict]:
    """Deliberately diverge today's feed so diff produces realistic buckets."""
    random.seed(44)
    yesterday = deepcopy(today)

    if len(yesterday) < 10:
        print("WARN: too few records for full diff scenario")
        return yesterday

    # 2 NEW today: drop these from yesterday
    drop_indices = random.sample(range(len(yesterday)), 2)
    yesterday = [r for i, r in enumerate(yesterday) if i not in drop_indices]

    # 2 RESOLVED today: invent records that were in yesterday but not today.
    # RxCUIs use openFDA-Label-indexed values (verified 2026-05-01 — RxNorm canonical IDs
    # like 6851/11202 don't appear in openFDA labels; label DB indexes by clinical-drug concept).
    invented = [
        {
            "generic_name": "FAKE_RESOLVED_A — methotrexate IV",
            "status": "Current",
            "openfda": {"rxcui": ["105585"]},   # methotrexate label-indexed RxCUI
            "shortage_reason": "Demand increase for the drug",
        },
        {
            "generic_name": "FAKE_RESOLVED_B — vincristine sulfate",
            "status": "Current",
            "openfda": {"rxcui": ["1863343"]},  # vincristine label-indexed RxCUI
            "shortage_reason": "Manufacturing delay",
        },
    ]
    yesterday.extend(invented)

    # 1 RE-OCCURRENCE: yesterday=Resolved, today=Current → triggers rubric Rule C3.
    # 1 MODERATE ESCALATION: yesterday=Available with limitations (synthetic), today=Current.
    if len(yesterday) >= 4:
        flip_indices = random.sample(range(len(yesterday) - 2), 2)
        yesterday[flip_indices[0]]["status"] = "Resolved"
        yesterday[flip_indices[1]]["status"] = "Available with limitations"

    return yesterday


if __name__ == "__main__":
    if OUT_PATH.exists():
        print(f"{OUT_PATH} already exists. Skipping (R6 mitigation: do not overwrite).")
        print("Delete the file manually if you want to regenerate.")
        sys.exit(0)

    print("Fetching today's live FDA shortage feed (status:Current)...")
    today = fetch_current_feed(60)
    print(f"Today: {len(today)} records.")

    yesterday = make_yesterday(today)

    snapshot = {
        "snapshot_date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
        "label": "SYNTHETIC — fictional yesterday for diff seeding",
        "results": yesterday,
    }

    OUT_PATH.write_text(json.dumps(snapshot, indent=2))
    print(f"Wrote {OUT_PATH} ({len(yesterday)} records).")
    print("\nDiff scenarios baked in:")
    print("  - 2 records in today but not yesterday → NEW shortages bucket")
    print("  - 2 records in yesterday but not today → RESOLVED bucket")
    print("  - 1 record yesterday=Resolved, today=Current → rubric Rule C3 (re-occurrence → Critical)")
    print("  - 1 record yesterday='Available with limitations', today=Current → moderate escalation")
