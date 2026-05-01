# Phase 01 — Data Layer
**Covers**: ROADMAP H0 (Setup) + H1 (Data Layer)
**Time budget**: 60 min total (H0: 0–15 min, H1: 15–60 min)
**Working directory**: `/Users/anton/Downloads/Rx-Shortage-Intelligence`

---

## Resolved questions (Option A for all Q1–Q4)

| # | Question | Decision |
|---|----------|----------|
| Q1 | TBD status handling | Filter to `status:Current` only; TBD → v0.2 |
| Q2 | One-shortage → many-RxCUIs | Keep list shape; index by every RxCUI in list |
| Q3 | Synthetic formulary alternatives | Hand-populate 5 demo drugs; leave remaining 25 empty |
| Q4 | Cost target | Report `~$0.10/briefing` for v0.1; v0.2 path = mixture-of-models → `$0.04` |
| Q5 | Scope | Full repo skeleton (H0) + data layer (H1) |
| Q6 | `yesterday_snapshot.json` | Already exists (4,634 lines); leave as-is per R6 mitigation |
| Q7 | `cache.py` | Include in this phase |
| Q8 | Working dir + `.env` | Use `/Users/anton/Downloads/Rx-Shortage-Intelligence`; create `.env.template` |

---

## Phase goal

At the end of this phase, running `python -m src.data_loader` will:
1. Fetch live FDA shortage feed
2. Write `data/synthetic_formulary.json` (30 drugs sampled from live feed, 5 with `preferred_alternatives` populated)
3. Write `data/active_orders.json` (random orders per drug)
4. Skip regenerating `data/yesterday_snapshot.json` (already exists)
5. Print a summary showing drug counts, FDA overlap count (≥5), and formulary preview

All subsequent `src/` modules exist as stubs so `python -c "import src.agent, src.briefing, src.mcp_bridge"` works without error.

---

## Task breakdown

### Block 1 — H0: Environment & skeleton (≤15 min)

#### Task 1.1 — Python venv + dependencies
```bash
cd /Users/anton/Downloads/Rx-Shortage-Intelligence
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Verify
python -c "import anthropic, mcp, streamlit, diskcache, httpx, fastmcp; print('ok')"
```
Expected output: `ok`

#### Task 1.2 — `.env` setup
Create `.env.template` (committed) and `.env` (gitignored, personal).

`.env.template` content:
```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` — copy from template and fill in real key:
```bash
cp .env.template .env
# Edit .env: set ANTHROPIC_API_KEY=<your real key>
```

Verify `.gitignore` already excludes `.env` (it does — pre-existing `.gitignore`).

#### Task 1.3 — Full `src/` skeleton

Create the following files. All stubs contain only a module docstring + `pass` or empty body so imports work cleanly.

**Directory tree to create:**
```
src/
  __init__.py
  main.py
  agent.py
  mcp_bridge.py
  briefing.py
  cache.py              ← real implementation (Task 2.1)
  data_loader.py        ← real implementation (Task 2.2)
  servers/
    __init__.py
    fda_shortage_server.py
    drug_label_server.py
    rxnorm_server.py
  eval/
    __init__.py
    runner.py
    cases.json
data/
  briefings/            ← empty dir, .gitkeep
cache/
  api/                  ← empty dir, .gitkeep (diskcache writes here)
```

**Files with stub content** (anything not `cache.py` or `data_loader.py`):

`src/__init__.py` — empty

`src/main.py`:
```python
"""Streamlit entry point — implemented in H5."""
```

`src/agent.py`:
```python
"""Tool-use loop — implemented in H3."""
```

`src/mcp_bridge.py`:
```python
"""FastMCP Client bridge — implemented in H2."""
```

`src/briefing.py`:
```python
"""Briefing generation + diff logic — implemented in H4."""
```

`src/servers/__init__.py` — empty

`src/servers/fda_shortage_server.py`:
```python
"""FDA shortage MCP server — implemented in H2."""
```

`src/servers/drug_label_server.py`:
```python
"""openFDA label MCP server — implemented in H2."""
```

`src/servers/rxnorm_server.py`:
```python
"""RxNorm + RxClass MCP server — implemented in H2."""
```

`src/eval/__init__.py` — empty

`src/eval/runner.py`:
```python
"""Eval harness — implemented in H6."""
```

`src/eval/cases.json` — copy from `research/06-eval-harness/POC-eval-cases.json`.

`data/briefings/.gitkeep` — empty file
`cache/api/.gitkeep` — empty file

**Verify skeleton imports:**
```bash
python -c "import src.agent, src.briefing, src.mcp_bridge; print('stubs ok')"
```

---

### Block 2 — H1: `cache.py` (≤10 min)

#### Task 2.1 — Write `src/cache.py`

**What it does**: wraps `diskcache.Cache` with a `cached_get()` helper so every API call goes through disk cache. Single module-level `Cache` instance pointing at `cache/api/`.

**Key design decisions** (from context7 docs + research):
- Module-level singleton `Cache` — thread-safe, process-safe, persists across runs
- `expire` in seconds — FDA shortage feed: 3600 (1 hr TTL); RxNorm: 86400 (24 hr TTL); openFDA labels: 86400 (24 hr TTL)
- Sentinel pattern for `None` results — if a drug has no label, cache that `None` to avoid re-fetching on every run
- Key format: `"<namespace>:<unique_id>"` — e.g. `"fda_shortages:status:Current:limit:100"`, `"label:rxcui:2555"`

**Implementation spec:**

```python
# src/cache.py
"""
Disk-backed API cache using diskcache.

Usage:
    from src.cache import cached_get

    data = cached_get(
        key="fda_shortages:current:100",
        fetch_fn=lambda: httpx.get(...).json(),
        ttl=3600,
    )

TTLs:
    FDA shortage feed   : 3600 s  (1 hr)  — changes daily at most
    openFDA label       : 86_400 s (24 hr) — very stable
    RxNorm/RxClass      : 86_400 s (24 hr) — very stable
"""

from pathlib import Path
from diskcache import Cache

# TTL constants (seconds) — importable by other modules
TTL_FDA_SHORTAGES = 3_600
TTL_OPENFDA_LABEL = 86_400
TTL_RXNORM        = 86_400

_MISS = object()  # sentinel: distinguishes cache miss from cached-None

_CACHE_DIR = Path(__file__).parent.parent / "cache" / "api"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_cache: Cache = Cache(str(_CACHE_DIR), size_limit=int(500e6))  # 500 MB cap


def cached_get(key: str, fetch_fn, ttl: int) -> any:
    """
    Return cached value for `key`, or call `fetch_fn()`, cache result, return it.
    Caches None results (sentinel pattern) so failed lookups aren't re-fetched.

    Args:
        key:      cache key string, format "<namespace>:<id>"
        fetch_fn: zero-arg callable that returns the value to cache
        ttl:      seconds until expiry

    Returns:
        Cached or freshly-fetched value (may be None for not-found results).
    """
    value = _cache.get(key, default=_MISS)
    if value is not _MISS:
        return value  # cache hit (including cached None)

    value = fetch_fn()
    _cache.set(key, value, expire=ttl)
    return value


def clear_key(key: str) -> None:
    """Remove a specific key from cache (force re-fetch on next call)."""
    _cache.delete(key)


def cache_info() -> dict:
    """Return basic cache stats for smoke-test / diagnostics."""
    return {
        "directory": str(_CACHE_DIR),
        "size_bytes": _cache.volume(),
        "item_count": len(_cache),
    }
```

**Smoke test** (inline):
```bash
python -c "
from src.cache import cached_get, cache_info, TTL_FDA_SHORTAGES
result = cached_get('test:ping', lambda: {'ok': True}, ttl=60)
print('cache hit:', cached_get('test:ping', lambda: {'WRONG': True}, ttl=60))
print(cache_info())
"
```
Expected: `cache hit: {'ok': True}` — second call returns cached value, not `{'WRONG': True}`.

---

### Block 3 — H1: `data_loader.py` (≤30 min)

#### Task 3.1 — Write `src/data_loader.py`

**What it does**:
1. Fetches live FDA shortage feed (via `cache.py`, TTL 1 hr)
2. Samples 30 drugs with RxCUIs to form the synthetic formulary
3. For 5 demo drugs: fetches RxClass ATC class members as `preferred_alternatives`
4. Writes `data/synthetic_formulary.json`
5. Writes `data/active_orders.json`
6. Skips `data/yesterday_snapshot.json` if already exists (R6 mitigation)
7. Verifies FDA overlap ≥ 5 before exit

**Implementation spec:**

```python
# src/data_loader.py
"""
Bootstrap synthetic data files from live FDA shortage feed.

Run:  python -m src.data_loader

Outputs (only writes if files missing, except formulary + orders which regenerate):
  data/synthetic_formulary.json
  data/active_orders.json
  data/yesterday_snapshot.json  ← SKIPPED if already exists (R6 mitigation)

Q1 decision: status:Current only. TBD → v0.2.
Q2 decision: keep full rxcui list; index_by_rxcui() indexes every entry.
Q3 decision: hand-populate preferred_alternatives for 5 demo drugs only.
"""

import httpx
import json
import random
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.cache import cached_get, TTL_FDA_SHORTAGES, TTL_RXNORM

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

FORMULARY_PATH  = DATA_DIR / "synthetic_formulary.json"
ORDERS_PATH     = DATA_DIR / "active_orders.json"
YESTERDAY_PATH  = DATA_DIR / "yesterday_snapshot.json"

# ── Constants ──────────────────────────────────────────────────────────────
FDA_SHORTAGES_URL = "https://api.fda.gov/drug/shortages.json"
RXCLASS_BASE      = "https://rxnav.nlm.nih.gov/REST/rxclass"
RXNORM_BASE       = "https://rxnav.nlm.nih.gov/REST"

ROUTES   = ["IV", "IM", "PO", "SubQ", "Inhalation", "Topical"]
DEPTS    = ["ICU", "Oncology", "ER", "Med-Surg", "Pediatrics", "Surgery", "Ambulatory"]
STATUSES = ["preferred", "non-preferred", "restricted", "non-formulary"]

# Q3: 5 demo drugs for which we hand-populate preferred_alternatives via RxClass.
# These are sampled from shortage-prone drug classes; RxClass ATC will be used at runtime.
# Identified from typical FDA shortage feed content (oncology + critical-care focus).
DEMO_DRUG_NAMES = [
    "cisplatin",
    "methotrexate",
    "carboplatin",
    "vincristine",
    "morphine",
]


# ── FDA shortage fetch ─────────────────────────────────────────────────────

def _fetch_shortages_raw(limit: int = 100) -> list[dict]:
    """Fetch current shortage records from openFDA. Cached 1 hr."""
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
    """Strip openFDA noise. Keep only fields data_loader needs.
    Q2: preserves rxcui as a list (may be multi-element).
    """
    openfda = record.get("openfda") or {}
    return {
        "generic_name":   record.get("generic_name", "Unknown"),
        "status":         record.get("status", ""),
        "shortage_reason": record.get("shortage_reason", ""),
        "rxcui":          openfda.get("rxcui") or [],       # list, may be empty
        "brand_name":     (openfda.get("brand_name") or [""])[0],
        "route":          (openfda.get("route") or [""])[0],
    }


def sample_drugs_from_feed(target: int = 30) -> list[dict]:
    """Return up to `target` trimmed shortage records that have ≥1 RxCUI."""
    raw = _fetch_shortages_raw(limit=100)
    seen = set()
    drugs = []
    for rec in raw:
        trimmed = _trim(rec)
        rxcuis = trimmed["rxcui"]
        if not rxcuis:
            continue
        primary = rxcuis[0]
        if primary in seen:
            continue
        seen.add(primary)
        drugs.append(trimmed)
        if len(drugs) >= target:
            break
    return drugs


def index_by_rxcui(drugs: list[dict]) -> dict[str, dict]:
    """Q2: Build lookup dict. Each RxCUI in the list maps to its drug record.
    One shortage record → N index entries (all RxCUIs in the list).
    """
    idx = {}
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
        items = (resp.json().get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo") or []
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
    """Return list of alternative drug names from same ATC class.
    Returns [] if RxNorm/RxClass lookup fails (no crash).
    Confidence label: 'class-member' (not 'equivalent') — per TRADEOFFS.md.
    """
    try:
        rxcui = _normalize_to_rxcui(drug_name)
        if not rxcui:
            return []
        cls = _get_atc_class(rxcui)
        if not cls:
            return []
        members = _get_class_members(cls["classId"])
        # Exclude the source drug itself; return names only
        return [
            m["name"] for m in members
            if m.get("name") and m.get("rxcui") != rxcui
        ][:10]  # cap at 10 to keep formulary JSON readable
    except Exception:
        return []  # never crash data_loader over alternatives


# ── Synthetic data generation ──────────────────────────────────────────────

def synthesize_formulary(drugs: list[dict]) -> dict:
    """Build synthetic_formulary.json from sampled shortage drugs.
    Q3: populate preferred_alternatives for DEMO_DRUG_NAMES only.
    """
    random.seed(42)
    now = datetime.now(timezone.utc).isoformat()

    # Pre-fetch alternatives for demo drugs
    demo_alts: dict[str, list[str]] = {}
    for name in DEMO_DRUG_NAMES:
        alts = fetch_class_alternatives(name)
        if alts:
            demo_alts[name.lower()] = alts
            print(f"  Alternatives for {name}: {alts[:3]}{'...' if len(alts) > 3 else ''}")
        else:
            demo_alts[name.lower()] = []
            print(f"  Alternatives for {name}: (none found)")

    formulary_drugs = []
    for d in drugs:
        name_lower = d["generic_name"].lower()
        # Match demo drug by name substring (e.g. "Cisplatin Injection" → "cisplatin")
        alts = next(
            (v for k, v in demo_alts.items() if k in name_lower),
            []
        )
        # Use route from FDA record if present, else random
        route = d["route"] if d["route"] else random.choice(ROUTES)
        formulary_drugs.append({
            "rxcui":                  d["rxcui"][0] if d["rxcui"] else "",
            "rxcui_list":             d["rxcui"],     # Q2: preserve full list
            "name":                   d["generic_name"],
            "formulary_status":       random.choice(STATUSES),
            "route_of_administration": route,
            "therapeutic_class":      "TBD",          # filled by rxnorm_server at runtime
            "restriction_criteria":   random.choice([
                None, "Specialist only", "Oncology only",
                "ICU only", "Age >18", "Renal-dosed",
            ]),
            "preferred_alternatives": alts,            # Q3: populated for demo drugs only
            "alternatives_confidence": "class-member" if alts else None,
            "last_pt_review_date":    "2026-01-15",
        })

    return {
        "customer_id":    "memorial-health-450",
        "label":          "SYNTHETIC — for v0.1 demo only",
        "generated_at":   now,
        "drugs":          formulary_drugs,
    }


def synthesize_orders(drugs: list[dict]) -> dict:
    """Build active_orders.json."""
    random.seed(43)
    orders = [
        {
            "rxcui":               d["rxcui"][0] if d["rxcui"] else "",
            "count_last_30_days":  random.randint(0, 80),
            "departments":         random.sample(DEPTS, k=random.randint(1, 3)),
        }
        for d in drugs
    ]
    return {
        "customer_id":    "memorial-health-450",
        "snapshot_date":  datetime.now(timezone.utc).date().isoformat(),
        "label":          "SYNTHETIC",
        "orders":         orders,
    }


def generate_yesterday_snapshot(today_drugs: list[dict]) -> dict:
    """Generate yesterday_snapshot.json with deliberate diff scenarios.
    Only called if file is missing (R6 mitigation: caller checks).
    Produces: 2 new, 2 resolved, 1 re-occurrence, 1 moderate escalation.
    """
    random.seed(44)
    yesterday = deepcopy(today_drugs)

    if len(yesterday) < 10:
        print("  WARN: too few records for full diff scenario — using as-is")
        return {
            "snapshot_date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
            "label":         "SYNTHETIC — fictional yesterday for diff seeding",
            "results":       yesterday,
        }

    # 2 NEW today: drop these records from yesterday
    drop_idx = random.sample(range(len(yesterday)), 2)
    yesterday = [r for i, r in enumerate(yesterday) if i not in drop_idx]

    # 2 RESOLVED: invent records in yesterday that won't be in today
    invented = [
        {
            "generic_name": "FAKE_RESOLVED_A — methotrexate IV",
            "status": "Current",
            "openfda": {"rxcui": ["105585"]},
            "shortage_reason": "Demand increase for the drug",
        },
        {
            "generic_name": "FAKE_RESOLVED_B — vincristine sulfate",
            "status": "Current",
            "openfda": {"rxcui": ["1863343"]},
            "shortage_reason": "Manufacturing delay",
        },
    ]
    yesterday.extend(invented)

    # 1 RE-OCCURRENCE (yesterday=Resolved) + 1 MODERATE ESCALATION
    if len(yesterday) >= 4:
        flip_idx = random.sample(range(len(yesterday) - 2), 2)
        yesterday[flip_idx[0]]["status"] = "Resolved"
        yesterday[flip_idx[1]]["status"] = "Available with limitations"

    return {
        "snapshot_date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
        "label":         "SYNTHETIC — fictional yesterday for diff seeding",
        "results":       yesterday,
    }


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    print("=== Rx Shortage Intelligence — Data Loader ===\n")

    # Step 1: fetch live FDA shortage feed
    print("1. Fetching live FDA shortage feed (status:Current)...")
    drugs = sample_drugs_from_feed(30)
    print(f"   Sampled {len(drugs)} drugs with RxCUIs from live feed.\n")

    if len(drugs) < 5:
        print("ERROR: fewer than 5 drugs sampled — check FDA API connectivity.")
        return

    # Step 2: synthetic formulary (always regenerate)
    print("2. Building synthetic formulary (30 drugs, 5 with alternatives)...")
    formulary = synthesize_formulary(drugs)
    FORMULARY_PATH.write_text(json.dumps(formulary, indent=2))
    print(f"   Wrote {FORMULARY_PATH} ({len(formulary['drugs'])} drugs)\n")

    # Step 3: active orders (always regenerate)
    print("3. Building active orders...")
    orders = synthesize_orders(drugs)
    ORDERS_PATH.write_text(json.dumps(orders, indent=2))
    print(f"   Wrote {ORDERS_PATH} ({len(orders['orders'])} order records)\n")

    # Step 4: yesterday snapshot (skip if exists — R6 mitigation)
    if YESTERDAY_PATH.exists():
        print(f"4. yesterday_snapshot.json already exists — skipping (R6 mitigation).\n")
    else:
        print("4. Generating yesterday_snapshot.json...")
        snapshot = generate_yesterday_snapshot(drugs)
        YESTERDAY_PATH.write_text(json.dumps(snapshot, indent=2))
        print(f"   Wrote {YESTERDAY_PATH} ({len(snapshot['results'])} records)\n")

    # Step 5: verify overlap
    print("5. Verifying FDA overlap...")
    formulary_rxcuis = {d["rxcui"] for d in formulary["drugs"] if d["rxcui"]}
    fda_rxcuis = {rxcui for d in drugs for rxcui in d["rxcui"]}
    overlap = formulary_rxcuis & fda_rxcuis
    print(f"   Formulary RxCUIs: {len(formulary_rxcuis)}")
    print(f"   FDA feed RxCUIs:  {len(fda_rxcuis)}")
    print(f"   Overlap count:    {len(overlap)}")
    if len(overlap) < 5:
        print("   WARNING: overlap < 5 — briefing may be empty. Re-run or check sampling.")
    else:
        print("   ✓ Overlap ≥ 5 — exit criteria met.")

    # Step 6: preview
    print("\n6. Formulary preview (first 5 drugs):")
    for d in formulary["drugs"][:5]:
        alts = d["preferred_alternatives"]
        print(f"   {d['name'][:40]:<40} {d['formulary_status']:<15} "
              f"alts={len(alts)} {alts[:2]}")

    print("\n=== Data layer ready. ===")


if __name__ == "__main__":
    main()
```

---

### Block 4 — Verification

#### Exit criteria (from ROADMAP H1)
- [ ] `python -c "import anthropic, mcp, streamlit, diskcache; print('ok')"` prints `ok`
- [ ] `python -m src.data_loader` completes without error
- [ ] `data/synthetic_formulary.json` exists with 30 drugs
- [ ] `data/active_orders.json` exists with 30 records
- [ ] `data/yesterday_snapshot.json` exists (was pre-existing; preserved)
- [ ] At least 5 of the 30 formulary drugs overlap the live FDA shortage feed
- [ ] At least 1 of the 5 demo drugs has `preferred_alternatives` populated
- [ ] `python -c "from src.cache import cached_get, cache_info; print(cache_info())"` prints cache dir + stats

#### Smoke test sequence
```bash
cd /Users/anton/Downloads/Rx-Shortage-Intelligence
source venv/bin/activate

# 1. Stubs import cleanly
python -c "import src.agent, src.briefing, src.mcp_bridge, src.cache; print('stubs ok')"

# 2. Cache round-trip
python -c "
from src.cache import cached_get, cache_info
r = cached_get('test:ping', lambda: {'ok': True}, ttl=60)
assert r == {'ok': True}
r2 = cached_get('test:ping', lambda: {'WRONG': True}, ttl=60)
assert r2 == {'ok': True}, 'cache miss — sentinel broken'
print('cache ok', cache_info())
"

# 3. Full data loader
python -m src.data_loader
```

---

## Failure modes & mitigations

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `pip install` fails on `mcp[cli]` | pip version | `pip install --upgrade pip` first |
| FDA API returns empty list | Rate limit or network | Wait 60s, re-run; cache prevents repeat hits |
| `overlap < 5` warning | FDA feed structure changed | Check `_trim()` — confirm `openfda.rxcui` field still present |
| RxClass returns no alternatives for demo drugs | API schema change or no ATC entry | `fetch_class_alternatives()` returns `[]` silently — not a hard failure |
| `yesterday_snapshot.json` not regenerated | Already exists | Intentional (R6). Delete file manually if you want fresh scenarios |
| `import src.cache` fails | Venv not activated | `source venv/bin/activate` |

---

## Files created by this phase

| File | Written by | Notes |
|------|-----------|-------|
| `venv/` | Task 1.1 | Not committed |
| `.env` | Task 1.2 | Not committed |
| `.env.template` | Task 1.2 | Committed |
| `src/__init__.py` | Task 1.3 | Stub |
| `src/main.py` | Task 1.3 | Stub |
| `src/agent.py` | Task 1.3 | Stub |
| `src/mcp_bridge.py` | Task 1.3 | Stub |
| `src/briefing.py` | Task 1.3 | Stub |
| `src/servers/__init__.py` | Task 1.3 | Stub |
| `src/servers/fda_shortage_server.py` | Task 1.3 | Stub |
| `src/servers/drug_label_server.py` | Task 1.3 | Stub |
| `src/servers/rxnorm_server.py` | Task 1.3 | Stub |
| `src/eval/__init__.py` | Task 1.3 | Stub |
| `src/eval/runner.py` | Task 1.3 | Stub |
| `src/eval/cases.json` | Task 1.3 | Copy from research/06-eval-harness/ |
| `src/cache.py` | Task 2.1 | Real implementation |
| `src/data_loader.py` | Task 3.1 | Real implementation |
| `data/synthetic_formulary.json` | `data_loader.py` | Generated |
| `data/active_orders.json` | `data_loader.py` | Generated |
| `data/briefings/.gitkeep` | Task 1.3 | Empty dir marker |
| `cache/api/.gitkeep` | Task 1.3 | Empty dir marker |

**Not touched**: `data/yesterday_snapshot.json` (already exists, R6 preserved)

---

## Context7 library patterns used

Sourced from `httpx` + `diskcache` official docs via context7 MCP.

### httpx
- `httpx.get(url, params=dict, timeout=15)` — sync, no client context needed for one-off calls; module-level `Client` for reuse
- `if resp.status_code == 404: return None` before `resp.raise_for_status()` — 404 = not found, not error
- Catch `httpx.HTTPStatusError` for bad status, `httpx.RequestError` for network/timeout

### diskcache
- `Cache(path, size_limit=int(500e6))` — auto-creates dir, 500 MB cap, thread+process safe
- `cache.set(key, value, expire=seconds)` / `cache.get(key, default=_MISS)`
- Sentinel `_MISS = object()` distinguishes cache miss from a legitimately cached `None`
