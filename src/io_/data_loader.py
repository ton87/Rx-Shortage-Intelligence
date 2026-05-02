"""
Bootstrap synthetic data files from the live FDA shortage feed.

Run:  python -m src.data_loader

Outputs (generated fresh each run, except yesterday_snapshot.json):
  data/synthetic_formulary.json   — 30 drugs sampled from live FDA feed
  data/active_orders.json         — random order volume per drug
  data/yesterday_snapshot.json    — SKIPPED if already exists (R6 mitigation)

Design decisions (see QUESTIONS-FOR-ANTON.md):
  Q1: status:Current only — TBD records filtered out (v0.2 expansion)
  Q2: rxcui preserved as list; index_by_rxcui() maps every entry to its record
  Q3: preferred_alternatives populated for 5 demo drugs via RxClass ATC only
"""

import json
import random
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

from src.cache import cached_get, TTL_FDA_SHORTAGES, TTL_RXNORM

# ── Paths ──────────────────────────────────────────────────────────────────
# src/io_/data_loader.py → parent.parent.parent = repo root.
# Pre-Step 3 the file lived at src/data_loader.py and used parent.parent;
# the move broke this and silently resolved DATA_DIR to src/data.
ROOT     = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data"

FORMULARY_PATH = DATA_DIR / "synthetic_formulary.json"
ORDERS_PATH    = DATA_DIR / "active_orders.json"
YESTERDAY_PATH = DATA_DIR / "yesterday_snapshot.json"

# ── API endpoints ──────────────────────────────────────────────────────────
FDA_SHORTAGES_URL = "https://api.fda.gov/drug/shortages.json"
RXCLASS_BASE      = "https://rxnav.nlm.nih.gov/REST/rxclass"
RXNORM_BASE       = "https://rxnav.nlm.nih.gov/REST"

# ── Synthetic-data constants ───────────────────────────────────────────────
ROUTES   = ["IV", "IM", "PO", "SubQ", "Inhalation", "Topical"]
DEPTS    = ["ICU", "Oncology", "ER", "Med-Surg", "Pediatrics", "Surgery", "Ambulatory"]
STATUSES = ["preferred", "non-preferred", "restricted", "non-formulary"]

# Q3: names to match against FDA generic_name for alternatives pre-population.
# Substring match so "Cisplatin Injection" → "cisplatin" hits.
DEMO_DRUG_NAMES = ["cisplatin", "methotrexate", "carboplatin", "vincristine", "morphine"]


# ── FDA shortage helpers ───────────────────────────────────────────────────

def _fetch_shortages_raw(limit: int = 100) -> list[dict]:
    """Fetch current shortage records. Q1: status:Current only. Cached 1 hr."""
    cache_key = f"fda_shortages:current:{limit}"

    def _fetch():
        resp = httpx.get(
            FDA_SHORTAGES_URL,
            params={"search": "status:Current", "limit": limit},
            timeout=15,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("results", [])

    return cached_get(cache_key, _fetch, TTL_FDA_SHORTAGES)


def _trim(record: dict) -> dict:
    """Strip openFDA noise; keep only fields we need.
    Q2: rxcui stays a list — never coerced to scalar.
    """
    openfda = record.get("openfda") or {}
    return {
        "generic_name":    record.get("generic_name", "Unknown"),
        "status":          record.get("status", ""),
        "shortage_reason": record.get("shortage_reason", ""),
        "rxcui":           openfda.get("rxcui") or [],   # list, possibly empty
        "brand_name":      (openfda.get("brand_name") or [""])[0],
        "route":           (openfda.get("route") or [""])[0],
    }


def sample_drugs_from_feed(target: int = 30) -> list[dict]:
    """Return up to `target` trimmed shortage records that have ≥1 RxCUI."""
    raw = _fetch_shortages_raw(limit=100)
    seen: set[str] = set()
    drugs: list[dict] = []
    for rec in raw:
        trimmed = _trim(rec)
        if not trimmed["rxcui"]:
            continue
        primary = trimmed["rxcui"][0]
        if primary in seen:
            continue
        seen.add(primary)
        drugs.append(trimmed)
        if len(drugs) >= target:
            break
    return drugs


def index_by_rxcui(drugs: list[dict]) -> dict[str, dict]:
    """Q2: Map every RxCUI in each record's list to that record.
    One shortage record → N index entries, so no formulary lookup can miss.
    """
    idx: dict[str, dict] = {}
    for drug in drugs:
        for rxcui in drug["rxcui"]:
            idx[rxcui] = drug
    return idx


# ── RxClass alternatives (Q3 — 5 demo drugs only) ─────────────────────────

def _normalize_to_rxcui(name: str) -> str | None:
    """Drug name → canonical RxCUI via RxNorm. Cached 24 hr."""
    cache_key = f"rxnorm:name:{name.lower()}"

    def _fetch():
        resp = httpx.get(
            f"{RXNORM_BASE}/rxcui.json",
            params={"name": name},
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        ids = (resp.json().get("idGroup") or {}).get("rxnormId") or []
        return ids[0] if ids else None

    return cached_get(cache_key, _fetch, TTL_RXNORM)


def _get_atc_class(rxcui: str) -> dict | None:
    """RxCUI → first ATC therapeutic class. Cached 24 hr."""
    cache_key = f"rxclass:atc:{rxcui}"

    def _fetch():
        resp = httpx.get(
            f"{RXCLASS_BASE}/class/byRxcui.json",
            params={"rxcui": rxcui, "relaSource": "ATC"},
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        items = (
            (resp.json().get("rxclassDrugInfoList") or {})
            .get("rxclassDrugInfo") or []
        )
        return items[0].get("rxclassMinConceptItem") if items else None

    return cached_get(cache_key, _fetch, TTL_RXNORM)


def _get_class_members(class_id: str) -> list[dict]:
    """ATC classId → list of member drug concepts. Cached 24 hr."""
    cache_key = f"rxclass:members:{class_id}"

    def _fetch():
        resp = httpx.get(
            f"{RXCLASS_BASE}/classMembers.json",
            params={"classId": class_id, "relaSource": "ATC"},
            timeout=15,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        items = (resp.json().get("drugMemberGroup") or {}).get("drugMember") or []
        return [item.get("minConcept") for item in items if item.get("minConcept")]

    return cached_get(cache_key, _fetch, TTL_RXNORM)


def fetch_class_alternatives(drug_name: str) -> list[str]:
    """Return up to 10 alternative drug names from the same ATC class.
    Returns [] on any failure — never crashes the loader.
    Confidence label: 'class-member', NOT 'equivalent' (per TRADEOFFS.md).
    """
    try:
        rxcui = _normalize_to_rxcui(drug_name)
        if not rxcui:
            return []
        cls = _get_atc_class(rxcui)
        if not cls:
            return []
        members = _get_class_members(cls["classId"])
        return [
            m["name"]
            for m in members
            if m.get("name") and m.get("rxcui") != rxcui
        ][:10]
    except Exception:
        return []  # never let alternatives fetch crash the data loader


# ── Synthetic data builders ────────────────────────────────────────────────

def synthesize_formulary(drugs: list[dict]) -> dict:
    """Build synthetic_formulary.json.
    Q3: preferred_alternatives populated for DEMO_DRUG_NAMES only.
    """
    random.seed(42)
    now = datetime.now(timezone.utc).isoformat()

    # Pre-fetch alternatives for the 5 demo drugs
    demo_alts: dict[str, list[str]] = {}
    for name in DEMO_DRUG_NAMES:
        alts = fetch_class_alternatives(name)
        demo_alts[name.lower()] = alts
        status = f"{alts[:2]}{'...' if len(alts) > 2 else ''}" if alts else "(none found)"
        print(f"   Alternatives for {name}: {status}")

    formulary_drugs = []
    for d in drugs:
        name_lower = d["generic_name"].lower()
        # Match by substring so "Cisplatin Injection" hits "cisplatin"
        alts = next(
            (v for k, v in demo_alts.items() if k in name_lower),
            [],
        )
        route = d["route"] if d["route"] else random.choice(ROUTES)
        formulary_drugs.append({
            "rxcui":                   d["rxcui"][0] if d["rxcui"] else "",
            "rxcui_list":              d["rxcui"],        # Q2: full list preserved
            "name":                    d["generic_name"],
            "formulary_status":        random.choice(STATUSES),
            "route_of_administration": route,
            "therapeutic_class":       "TBD",             # filled by rxnorm_server at H2
            "restriction_criteria":    random.choice([
                None, "Specialist only", "Oncology only",
                "ICU only", "Age >18", "Renal-dosed",
            ]),
            "preferred_alternatives":  alts,
            "alternatives_confidence": "class-member" if alts else None,
            "last_pt_review_date":     "2026-01-15",
        })

    return {
        "customer_id":  "memorial-health-450",
        "label":        "SYNTHETIC — for v0.1 demo only",
        "generated_at": now,
        "drugs":        formulary_drugs,
    }


def synthesize_orders(drugs: list[dict]) -> dict:
    """Build active_orders.json."""
    random.seed(43)
    orders = [
        {
            "rxcui":              d["rxcui"][0] if d["rxcui"] else "",
            "count_last_30_days": random.randint(0, 80),
            "departments":        random.sample(DEPTS, k=random.randint(1, 3)),
        }
        for d in drugs
    ]
    return {
        "customer_id":   "memorial-health-450",
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "label":         "SYNTHETIC",
        "orders":        orders,
    }


def generate_yesterday_snapshot(today_drugs: list[dict]) -> dict:
    """Generate yesterday_snapshot.json with deliberate diff scenarios.
    Only called if file is missing (caller checks — R6 mitigation).

    Diff baked in:
      - 2 NEW shortages  (records in today but not yesterday)
      - 2 RESOLVED       (records invented in yesterday; absent from today)
      - 1 RE-OCCURRENCE  (yesterday=Resolved → today=Current → Rule C3)
      - 1 ESCALATION     (yesterday=Available with limitations → today=Current)
    """
    random.seed(44)
    yesterday = deepcopy(today_drugs)

    if len(yesterday) < 10:
        print("   WARN: <10 records — diff scenarios may be sparse.")
        return {
            "snapshot_date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
            "label":         "SYNTHETIC — fictional yesterday for diff seeding",
            "results":       yesterday,
        }

    # 2 NEW today → drop from yesterday
    drop_idx = set(random.sample(range(len(yesterday)), 2))
    yesterday = [r for i, r in enumerate(yesterday) if i not in drop_idx]

    # 2 RESOLVED → invent records that won't appear in today's live feed.
    # Use _trim()-shaped records (rxcui as top-level list, no openfda wrapper)
    # so all consumers can access record["rxcui"] uniformly.
    yesterday.extend([
        {
            "generic_name":    "FAKE_RESOLVED_A — methotrexate IV",
            "status":          "Current",
            "shortage_reason": "Demand increase for the drug",
            "rxcui":           ["105585"],
            "brand_name":      "",
            "route":           "",
        },
        {
            "generic_name":    "FAKE_RESOLVED_B — vincristine sulfate",
            "status":          "Current",
            "shortage_reason": "Manufacturing delay",
            "rxcui":           ["1863343"],
            "brand_name":      "",
            "route":           "",
        },
    ])

    # 1 RE-OCCURRENCE + 1 ESCALATION → flip statuses on two remaining records
    if len(yesterday) >= 4:
        flip_idx = random.sample(range(len(yesterday) - 2), 2)
        yesterday[flip_idx[0]]["status"] = "Resolved"
        yesterday[flip_idx[1]]["status"] = "Available with limitations"

    return {
        "snapshot_date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
        "label":         "SYNTHETIC — fictional yesterday for diff seeding",
        "results":       yesterday,
    }


# ── Public I/O helpers (no Streamlit — decorators live in main.py) ─────────

def _yesterday_record(rec: dict) -> dict:
    """Lift openfda.rxcui to the top level so compute_diff can index by it.

    Yesterday's snapshot is the raw FDA API shape (rxcui nested under
    `openfda`). The trim mirrors what fda_shortage_server._trim does for
    today's records, just enough that compute_diff sees the same key shape
    on both sides of the diff.
    """
    rxcui = (rec.get("openfda") or {}).get("rxcui", []) or []
    if not isinstance(rxcui, list):
        rxcui = [rxcui]
    return {**rec, "rxcui": rxcui}


def load_briefing_inputs() -> tuple[list, list, list]:
    """Return (formulary_drugs, orders, yesterday_shortages).

    Yesterday key in the snapshot file is `results` (raw FDA API name); each
    record is normalized so its `rxcui` field is a top-level list, matching
    today's trimmed records.
    """
    formulary = json.loads((DATA_DIR / "synthetic_formulary.json").read_text())["drugs"]
    orders_data = json.loads((DATA_DIR / "active_orders.json").read_text())["orders"]
    yesterday_path = DATA_DIR / "yesterday_snapshot.json"
    if yesterday_path.exists():
        raw = json.loads(yesterday_path.read_text()).get("results", [])
        yesterday = [_yesterday_record(r) for r in raw]
    else:
        yesterday = []
    return formulary, orders_data, yesterday


def load_formulary() -> list[dict]:
    """Return the drugs list from synthetic_formulary.json."""
    formulary_path = DATA_DIR / "synthetic_formulary.json"
    if not formulary_path.exists():
        return []
    return json.loads(formulary_path.read_text()).get("drugs", [])


def load_orders_index() -> dict:
    """Return {rxcui: order} mapping from active_orders.json."""
    orders_path = DATA_DIR / "active_orders.json"
    if not orders_path.exists():
        return {}
    data = json.loads(orders_path.read_text())
    return {str(o["rxcui"]): o for o in data.get("orders", [])}


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    print("=== Rx Shortage Intelligence — Data Loader ===\n")

    # 1. Live FDA feed
    print("1. Fetching live FDA shortage feed (status:Current)...")
    drugs = sample_drugs_from_feed(30)
    print(f"   Sampled {len(drugs)} drugs with RxCUIs.\n")

    if len(drugs) < 5:
        print("ERROR: fewer than 5 drugs sampled — check FDA API connectivity.")
        return

    # 2. Synthetic formulary
    print("2. Building synthetic formulary (30 drugs, 5 with alternatives)...")
    formulary = synthesize_formulary(drugs)
    FORMULARY_PATH.write_text(json.dumps(formulary, indent=2))
    print(f"   Wrote {FORMULARY_PATH} ({len(formulary['drugs'])} drugs)\n")

    # 3. Active orders
    print("3. Building active orders...")
    orders = synthesize_orders(drugs)
    ORDERS_PATH.write_text(json.dumps(orders, indent=2))
    print(f"   Wrote {ORDERS_PATH} ({len(orders['orders'])} records)\n")

    # 4. Yesterday snapshot (skip if exists — R6 mitigation)
    if YESTERDAY_PATH.exists():
        print("4. yesterday_snapshot.json already exists — skipping (R6 mitigation).\n")
    else:
        print("4. Generating yesterday_snapshot.json...")
        snapshot = generate_yesterday_snapshot(drugs)
        YESTERDAY_PATH.write_text(json.dumps(snapshot, indent=2))
        print(f"   Wrote {YESTERDAY_PATH} ({len(snapshot['results'])} records)\n")

    # 5. Verify FDA overlap
    print("5. Verifying FDA overlap...")
    formulary_rxcuis = {d["rxcui"] for d in formulary["drugs"] if d["rxcui"]}
    fda_rxcuis       = {rxcui for d in drugs for rxcui in d["rxcui"]}
    overlap          = formulary_rxcuis & fda_rxcuis
    print(f"   Formulary RxCUIs : {len(formulary_rxcuis)}")
    print(f"   FDA feed RxCUIs  : {len(fda_rxcuis)}")
    print(f"   Overlap count    : {len(overlap)}")
    if len(overlap) < 5:
        print("   WARNING: overlap < 5 — briefing may be empty. Re-run or inspect feed.")
    else:
        print("   OK — overlap >= 5, exit criteria met.")

    # 6. Preview
    print("\n6. Formulary preview (first 5 drugs):")
    for d in formulary["drugs"][:5]:
        alts  = d["preferred_alternatives"]
        name  = d["name"][:38]
        fstat = d["formulary_status"]
        print(f"   {name:<38}  {fstat:<16}  alts={len(alts)} {alts[:2]}")

    print("\n=== Data layer ready. ===")


if __name__ == "__main__":
    main()
