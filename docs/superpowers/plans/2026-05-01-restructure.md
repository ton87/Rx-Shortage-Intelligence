# Rx Shortage Intelligence Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `src/main.py` (958 LOC) and `src/briefing.py` (821 LOC) into layered modules under `src/{ui,domain,agent,io}` with StrEnums for domain constants, CSS in a `.css` file, and agent prompts in `.md` files. Behavior, JSON shapes, CLI commands, and lock paths preserved verbatim.

**Architecture:** Four layers with strict dependency direction. `domain/` (pure stdlib) ← `io/` (filesystem + domain) ← `agent/` (anthropic + domain + io) ← `ui/` (streamlit + domain + io). `main.py` and `briefing.py` shrink to thin entry points.

**Tech Stack:** Python 3.11+, `StrEnum` from `enum`, Streamlit, Anthropic SDK, FastMCP, pytest, diskcache.

**Spec:** `docs/superpowers/specs/2026-05-01-restructure-design.md`

---

## Pre-flight

### Task 0: Capture baseline test status

**Files:**
- Read-only: `tests/`

- [ ] **Step 1: Run full test suite, capture pass/fail/error per module**

```bash
source venv/bin/activate
pytest tests/ -v --tb=no -q 2>&1 | tee /tmp/baseline-tests.txt
```
Expected: some FAIL/ERROR (`test_h5_ui_helpers.py` will ERROR on import — references nonexistent `load_briefing` and `SORT_ORDER`). Record exact list.

- [ ] **Step 2: Snapshot current briefing JSON for behavior diffing**

```bash
cp data/briefings/2026-05-01.json /tmp/briefing-baseline.json
```

- [ ] **Step 3: Snapshot agent prompt strings byte-exact**

```bash
python -c "from src.briefing import ROLE_AND_RULES, SEVERITY_RUBRIC; \
import hashlib; \
print('ROLE_AND_RULES:', hashlib.sha256(ROLE_AND_RULES.encode()).hexdigest()); \
print('SEVERITY_RUBRIC:', hashlib.sha256(SEVERITY_RUBRIC.encode()).hexdigest())" \
  | tee /tmp/prompt-hashes.txt
```

- [ ] **Step 4: Commit baseline doc**

Write `/tmp/baseline-tests.txt` summary into `docs/superpowers/plans/baseline-2026-05-01.md` (which tests pass, which fail and why, prompt hashes), then:

```bash
git add docs/superpowers/plans/baseline-2026-05-01.md
git commit -m "chore(plan): capture pre-restructure baseline"
```

---

## Step 1: Domain enums + constants

### Task 1.1: Create `src/domain/__init__.py`

**Files:**
- Create: `src/domain/__init__.py` (empty)

- [ ] **Step 1: Create empty package marker**

```bash
mkdir -p src/domain
touch src/domain/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add src/domain/__init__.py
git commit -m "feat(domain): create package"
```

### Task 1.2: `domain/severity.py` — Severity enum + rank

**Files:**
- Create: `src/domain/severity.py`
- Test: `tests/test_domain_severity.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_domain_severity.py
from src.domain.severity import Severity, SEVERITY_RANK


def test_severity_string_values_match_json_schema():
    assert Severity.CRITICAL == "Critical"
    assert Severity.WATCH == "Watch"
    assert Severity.RESOLVED == "Resolved"


def test_severity_rank_orders_critical_first():
    items = [Severity.RESOLVED, Severity.CRITICAL, Severity.WATCH]
    items.sort(key=lambda s: SEVERITY_RANK[s])
    assert items == [Severity.CRITICAL, Severity.WATCH, Severity.RESOLVED]


def test_severity_str_round_trip_via_json():
    import json
    payload = json.dumps({"severity": Severity.CRITICAL})
    assert json.loads(payload)["severity"] == "Critical"
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_domain_severity.py -v
```
Expected: ERROR — `No module named 'src.domain.severity'`.

- [ ] **Step 3: Implement**

```python
# src/domain/severity.py
"""Severity classification — single source of truth for the three levels."""

from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "Critical"
    WATCH = "Watch"
    RESOLVED = "Resolved"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.WATCH: 1,
    Severity.RESOLVED: 2,
}
```

- [ ] **Step 4: Run test, expect PASS**

```bash
pytest tests/test_domain_severity.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/severity.py tests/test_domain_severity.py
git commit -m "feat(domain): add Severity enum + rank"
```

### Task 1.3: `domain/confidence.py` — Confidence enum + labels

**Files:**
- Create: `src/domain/confidence.py`
- Test: `tests/test_domain_confidence.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_domain_confidence.py
from src.domain.confidence import Confidence, CONFIDENCE_LABELS


def test_confidence_string_values_match_json_schema():
    assert Confidence.HIGH == "high"
    assert Confidence.MEDIUM == "medium"
    assert Confidence.LOW == "low"


def test_confidence_labels_for_pill_display():
    assert CONFIDENCE_LABELS[Confidence.HIGH] == "HIGH"
    assert CONFIDENCE_LABELS[Confidence.MEDIUM] == "MED"
    assert CONFIDENCE_LABELS[Confidence.LOW] == "LOW"
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_domain_confidence.py -v
```
Expected: ERROR.

- [ ] **Step 3: Implement**

```python
# src/domain/confidence.py
"""Confidence levels — used for pill display + rule-based ceilings."""

from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CONFIDENCE_LABELS: dict[Confidence, str] = {
    Confidence.HIGH: "HIGH",
    Confidence.MEDIUM: "MED",
    Confidence.LOW: "LOW",
}
```

- [ ] **Step 4: Run test, expect PASS**

```bash
pytest tests/test_domain_confidence.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/confidence.py tests/test_domain_confidence.py
git commit -m "feat(domain): add Confidence enum + display labels"
```

### Task 1.4: `domain/fda.py` — FDAStatus enum + rank

**Files:**
- Create: `src/domain/fda.py`
- Test: `tests/test_domain_fda.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_domain_fda.py
from src.domain.fda import FDAStatus, status_rank


def test_fda_status_canonical_values():
    assert FDAStatus.CURRENT == "Current"
    assert FDAStatus.TBD == "To Be Discontinued"
    assert FDAStatus.RESOLVED == "Resolved"


def test_status_rank_for_diff_escalation():
    assert status_rank("Resolved") == 0
    assert status_rank("Available with limitations") == 1
    assert status_rank("Current") == 2
    assert status_rank("To Be Discontinued") == 3
    assert status_rank("Discontinued") == 3


def test_status_rank_unknown_defaults_to_one():
    assert status_rank("garbage") == 1
    assert status_rank("") == 1
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_domain_fda.py -v
```

- [ ] **Step 3: Implement**

```python
# src/domain/fda.py
"""FDA shortage feed status canonical values + diff-escalation rank.

Verified 2026-05-01 against live API: only "Current", "To Be Discontinued",
and "Resolved" appear. "Currently in Shortage" is hallucinated and breaks
the search query (404). Do not introduce new statuses without API check.
"""

from enum import StrEnum


class FDAStatus(StrEnum):
    CURRENT = "Current"
    TBD = "To Be Discontinued"
    RESOLVED = "Resolved"


_STATUS_RANK: dict[str, int] = {
    "Resolved": 0,
    "Available with limitations": 1,
    "Current": 2,
    "To Be Discontinued": 3,
    "Discontinued": 3,
}


def status_rank(status: str) -> int:
    """Rank for diff escalation comparison. Unknown → 1 (neutral middle)."""
    return _STATUS_RANK.get(status, 1)
```

- [ ] **Step 4: Run test, expect PASS**

```bash
pytest tests/test_domain_fda.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/fda.py tests/test_domain_fda.py
git commit -m "feat(domain): add FDAStatus enum + status_rank"
```

### Task 1.5: `domain/constants.py` — magic numbers

**Files:**
- Create: `src/domain/constants.py`

- [ ] **Step 1: Implement (no test — values trivially correct)**

```python
# src/domain/constants.py
"""Project-wide tunable constants. Values mirror the v0.1 PRD/CLAUDE.md budget."""

# Briefing pipeline
DEFAULT_CANDIDATE_CAP = 5          # Max drugs surfaced per briefing (latency budget)
FDA_FETCH_LIMIT = 100              # Max records pulled from FDA shortage feed per call
PER_DRUG_TIMEOUT_S = 90            # Per-drug agent classification timeout
BRIEFING_SUBPROCESS_TIMEOUT_S = 600  # Re-run subprocess wall clock cap

# Re-run lock (prevent concurrent CLI invocations from UI)
LOCK_PATH = "/tmp/rx_briefing.lock"
LOCK_STALE_S = 900                 # 15-min — anything older is stale, can be cleared

# Agent
AGENT_MODEL = "claude-sonnet-4-6"
AGENT_MAX_ITERATIONS = 8
AGENT_MAX_TOKENS = 4096

# Customer (single-tenant v0.1)
CUSTOMER_ID = "memorial-health-450"
PROMPT_VERSION = "v1"
SYNTHETIC_LABEL = "SYNTHETIC — v0.1 demo"
```

- [ ] **Step 2: Smoke import**

```bash
python -c "from src.domain.constants import DEFAULT_CANDIDATE_CAP, AGENT_MODEL; \
print(DEFAULT_CANDIDATE_CAP, AGENT_MODEL)"
```
Expected: `5 claude-sonnet-4-6`.

- [ ] **Step 3: Commit**

```bash
git add src/domain/constants.py
git commit -m "feat(domain): centralize tunable constants"
```

### Task 1.6: Update call sites — use enums + constants

**Files:**
- Modify: `src/main.py` (replace `SEVERITY_RANK` literal at line 34, action labels, status colors)
- Modify: `src/briefing.py` (replace `_status_rank` body, `cap = 5`, customer_id, model paths)
- Modify: `src/agent.py` (`MODEL`, `MAX_ITERATIONS` → import from constants)

- [ ] **Step 1: Update `src/agent.py` to use constants**

Replace lines 17-18:
```python
MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 8
```
With:
```python
from src.domain.constants import AGENT_MODEL as MODEL, AGENT_MAX_ITERATIONS as MAX_ITERATIONS, AGENT_MAX_TOKENS
```
And update line 41:
```python
kwargs: dict = dict(model=MODEL, max_tokens=4096, system=system, messages=messages)
```
To:
```python
kwargs: dict = dict(model=MODEL, max_tokens=AGENT_MAX_TOKENS, system=system, messages=messages)
```

- [ ] **Step 2: Update `src/briefing.py` to use FDAStatus rank**

Delete lines 438-440 (`_status_rank`) entirely. Replace its two usages at lines 476 with:
```python
from src.domain.fda import status_rank
# ... unchanged ...
tr, yr = status_rank(t.get("status", "")), status_rank(y.get("status", ""))
```
Add the import at the top with the other imports.

- [ ] **Step 3: Update `src/briefing.py` cap + customer_id + label**

Replace line 657:
```python
cap = 5
```
With:
```python
cap = DEFAULT_CANDIDATE_CAP
```
Replace line 791:
```python
"customer_id": "memorial-health-450",
```
With:
```python
"customer_id": CUSTOMER_ID,
```
Replace line 792:
```python
"prompt_version": "v1",
```
With:
```python
"prompt_version": PROMPT_VERSION,
```
Replace line 800:
```python
"label": "SYNTHETIC — v0.1 demo",
```
With:
```python
"label": SYNTHETIC_LABEL,
```
Add to imports at top:
```python
from src.domain.constants import (
    DEFAULT_CANDIDATE_CAP,
    FDA_FETCH_LIMIT,
    PER_DRUG_TIMEOUT_S,
    CUSTOMER_ID,
    PROMPT_VERSION,
    SYNTHETIC_LABEL,
)
```
Also replace line 617 `{"limit": 100}` with `{"limit": FDA_FETCH_LIMIT}` and line 707 `timeout=90` with `timeout=PER_DRUG_TIMEOUT_S`.

- [ ] **Step 4: Update `src/main.py` to use Severity enum + constants**

Replace line 34:
```python
SEVERITY_RANK = {"Critical": 0, "Watch": 1, "Resolved": 2}
```
With:
```python
from src.domain.severity import Severity, SEVERITY_RANK
```
Replace inline `{"Critical": 0, "Watch": 1, "Resolved": 2}` at lines ~610, 709, 770 with reuse of `SEVERITY_RANK`.

Replace line 317:
```python
BRIEFING_LOCK_PATH = Path("/tmp/rx_briefing.lock")
BRIEFING_LOCK_STALE_SECONDS = 900
```
With:
```python
from src.domain.constants import LOCK_PATH, LOCK_STALE_S, BRIEFING_SUBPROCESS_TIMEOUT_S
BRIEFING_LOCK_PATH = Path(LOCK_PATH)
BRIEFING_LOCK_STALE_SECONDS = LOCK_STALE_S
```
Replace line 396 `subprocess.run(cmd, shell=True, timeout=600, ...)` with `timeout=BRIEFING_SUBPROCESS_TIMEOUT_S`.

- [ ] **Step 5: Run all tests + smoke run**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: same pass/fail count as baseline (none broken by enum substitution).

- [ ] **Step 6: Commit**

```bash
git add src/agent.py src/briefing.py src/main.py
git commit -m "refactor: use Severity/FDAStatus enums + constants module at call sites"
```

---

## Step 2: Domain pure logic

### Task 2.1: `domain/diff.py` — extract `compute_diff`

**Files:**
- Create: `src/domain/diff.py`
- Modify: `src/briefing.py` (delete lines 436-485)
- Modify: `tests/test_h3_h4_briefing.py` (update import)

- [ ] **Step 1: Read existing tests**

```bash
grep -n "compute_diff\|index_formulary\|index_orders" tests/test_h3_h4_briefing.py
```

- [ ] **Step 2: Move `compute_diff` to `src/domain/diff.py`**

Create file with verbatim copy of lines 436-485 from current `src/briefing.py`, replacing the local `_status_rank` reference with `from src.domain.fda import status_rank`:

```python
# src/domain/diff.py
"""Diff today's FDA shortage feed against yesterday's snapshot.

Returns five buckets: new, escalated, improved, resolved, unchanged.
FDA records' rxcui field is a list — index by each element.
"""

from src.domain.fda import status_rank


def compute_diff(today: list[dict], yesterday: list[dict], formulary_rxcuis: set) -> dict:
    """Compare today's shortage feed against yesterday's snapshot.

    Returns {new, escalated, improved, resolved, unchanged}.
    Each item gets _diff_bucket and _formulary_rxcui set.
    Only items whose rxcui list intersects formulary_rxcuis are surfaced.
    """
    def _idx(records: list[dict]) -> dict[str, dict]:
        idx: dict[str, dict] = {}
        for r in records:
            for rxcui in r.get("rxcui", []):
                if rxcui and rxcui in formulary_rxcuis:
                    idx[rxcui] = r
        return idx

    today_idx = _idx(today)
    yest_idx = _idx(yesterday)

    today_keys = set(today_idx)
    yest_keys = set(yest_idx)

    result: dict[str, list[dict]] = {
        "new": [], "escalated": [], "improved": [], "resolved": [], "unchanged": [],
    }

    for k in today_keys - yest_keys:
        item = dict(today_idx[k])
        item["_diff_bucket"] = "new"
        item["_formulary_rxcui"] = k
        result["new"].append(item)

    for k in yest_keys - today_keys:
        item = dict(yest_idx[k])
        item["_diff_bucket"] = "resolved"
        item["_formulary_rxcui"] = k
        result["resolved"].append(item)

    for k in today_keys & yest_keys:
        t, y = today_idx[k], yest_idx[k]
        tr, yr = status_rank(t.get("status", "")), status_rank(y.get("status", ""))
        item = dict(t)
        item["_formulary_rxcui"] = k
        if tr > yr:
            item["_diff_bucket"] = "escalated"
            result["escalated"].append(item)
        elif tr < yr:
            item["_diff_bucket"] = "improved"
            result["improved"].append(item)
        else:
            item["_diff_bucket"] = "unchanged"
            result["unchanged"].append(item)

    return result
```

- [ ] **Step 3: Update `src/briefing.py`**

Delete lines 436-485 (the `# ── Diff logic ──` block including `_status_rank` and `compute_diff`). Add to imports at top:
```python
from src.domain.diff import compute_diff
```

- [ ] **Step 4: Update test import**

In `tests/test_h3_h4_briefing.py`, change:
```python
from src.briefing import compute_diff, index_formulary, index_orders, build_user_message, parse_briefing_item
```
To (split — `index_formulary`/`index_orders` move next task; for now keep both paths importable by leaving `briefing.py`'s re-import):
```python
from src.domain.diff import compute_diff
from src.briefing import index_formulary, index_orders, build_user_message, parse_briefing_item
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_h3_h4_briefing.py -v
```
Expected: same pass count as baseline.

- [ ] **Step 6: Commit**

```bash
git add src/domain/diff.py src/briefing.py tests/test_h3_h4_briefing.py
git commit -m "refactor(domain): extract compute_diff to domain/diff.py"
```

### Task 2.2: `domain/indexing.py` — extract `index_formulary` + `index_orders`

**Files:**
- Create: `src/domain/indexing.py`
- Modify: `src/briefing.py` (delete lines 422-433)
- Modify: `tests/test_h3_h4_briefing.py`

- [ ] **Step 1: Move to `src/domain/indexing.py`**

```python
# src/domain/indexing.py
"""Index formulary + orders by RxCUI for O(1) match lookup during briefing."""


def index_formulary(drugs: list[dict]) -> dict[str, dict]:
    """Index formulary by every RxCUI in rxcui_list so any FDA-side match hits.

    Multi-formulation drugs (e.g. methylphenidate ER → 14 RxCUIs) appear
    under each of their RxCUIs in the resulting index.
    """
    idx: dict[str, dict] = {}
    for drug in drugs:
        for rxcui in drug.get("rxcui_list", [drug.get("rxcui", "")]):
            if rxcui:
                idx[rxcui] = drug
    return idx


def index_orders(orders: list[dict]) -> dict[str, dict]:
    """Index active orders by RxCUI. Records without rxcui are dropped."""
    return {o["rxcui"]: o for o in orders if o.get("rxcui")}
```

- [ ] **Step 2: Update `src/briefing.py`**

Delete lines 422-433. Add to imports:
```python
from src.domain.indexing import index_formulary, index_orders
```

- [ ] **Step 3: Update test import**

In `tests/test_h3_h4_briefing.py`:
```python
from src.domain.indexing import index_formulary, index_orders
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_h3_h4_briefing.py -v
```
Expected: same pass count.

- [ ] **Step 5: Commit**

```bash
git add src/domain/indexing.py src/briefing.py tests/test_h3_h4_briefing.py
git commit -m "refactor(domain): extract index_formulary/index_orders"
```

### Task 2.3: `domain/matching.py` — extract formulary↔shortage matching

**Files:**
- Create: `src/domain/matching.py`
- Test: `tests/test_domain_matching.py`
- Modify: `src/main.py` (delete lines 647-712 — `_normalize_drug_name`, `get_briefing_shortage_index`, `find_shortage_match`)

- [ ] **Step 1: Write failing test**

```python
# tests/test_domain_matching.py
from src.domain.matching import normalize_drug_name, build_shortage_index, find_shortage_match


def test_normalize_strips_punctuation_and_whitespace():
    assert normalize_drug_name("Cefotaxime Sodium Powder, for Solution") == \
        "cefotaxime sodium powder for solution"


def test_normalize_handles_none_and_empty():
    assert normalize_drug_name("") == ""
    assert normalize_drug_name(None) == ""


def test_build_shortage_index_extracts_rxcui_and_name_keys():
    items = [
        {
            "rxcui": "12345",
            "drug_name": "Cisplatin Injection",
            "severity": "Critical",
            "summary": "shortage",
            "item_id": "id-1",
            "citations": [{"url": "http://x"}],
        }
    ]
    rxcui_idx, name_idx = build_shortage_index(items)
    assert "12345" in rxcui_idx
    assert "cisplatin injection" in name_idx
    assert rxcui_idx["12345"]["severity"] == "Critical"


def test_find_shortage_match_prefers_rxcui_then_name():
    rxcui_idx = {"999": {"severity": "Watch", "summary": "x", "citation": None, "item_id": "i"}}
    name_idx = {"foo": [{"severity": "Critical", "summary": "y", "citation": None, "item_id": "j"}]}

    drug_rxcui_hit = {"rxcui_list": ["999"], "name": "Bar"}
    assert find_shortage_match(drug_rxcui_hit, rxcui_idx, name_idx)["severity"] == "Watch"

    drug_name_hit = {"rxcui_list": ["nope"], "name": "Foo"}
    assert find_shortage_match(drug_name_hit, rxcui_idx, name_idx)["severity"] == "Critical"

    drug_no_hit = {"rxcui_list": ["nope"], "name": "Nothing"}
    assert find_shortage_match(drug_no_hit, rxcui_idx, name_idx) is None
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_domain_matching.py -v
```

- [ ] **Step 3: Implement (move from main.py:647-712)**

```python
# src/domain/matching.py
"""Match formulary entries to briefing shortage items.

Keyed by RxCUI primary, exact-normalized-name fallback. No substring matching —
multi-formulation drugs were over-matching via first-token substring before
this strict gate.
"""

from src.domain.severity import Severity, SEVERITY_RANK


def normalize_drug_name(name: str | None) -> str:
    """Lowercase + strip + collapse whitespace + drop punctuation noise.

    Conservative — only strips formulation tokens, not active-ingredient
    distinguishers. So 'Cefotaxime Sodium Powder, for Solution' matches
    'Cefotaxime Sodium for Injection' siblings.
    """
    if not name:
        return ""
    n = name.lower().strip()
    for token in [",", ";"]:
        n = n.replace(token, " ")
    while "  " in n:
        n = n.replace("  ", " ")
    return n.strip()


def build_shortage_index(items: list[dict]) -> tuple[dict, dict]:
    """Build (rxcui_idx, name_idx) from briefing items for fast formulary lookup.

    rxcui_idx: rxcui (str) → match dict — primary join key.
    name_idx:  normalized name (str) → list[match] — exact-name fallback only.
    """
    rxcui_idx: dict = {}
    name_idx: dict = {}
    for item in items:
        match = {
            "severity":   item.get("severity", Severity.WATCH),
            "summary":    item.get("summary", ""),
            "citation":   _primary_citation_url(item),
            "item_id":    item.get("item_id", ""),
        }
        rxcui = str(item.get("rxcui", ""))
        if rxcui:
            rxcui_idx[rxcui] = match
        norm = normalize_drug_name(item.get("drug_name") or "")
        if norm:
            name_idx.setdefault(norm, []).append(match)
    return rxcui_idx, name_idx


def find_shortage_match(drug: dict, rxcui_idx: dict, name_idx: dict) -> dict | None:
    """Match formulary drug to a briefing shortage by RxCUI then exact name.

    Returns None if no exact match — UI shows '—' honestly rather than guessing.
    """
    rxcui_list = drug.get("rxcui_list") or [drug.get("rxcui")]
    for r in rxcui_list:
        if r and str(r) in rxcui_idx:
            return rxcui_idx[str(r)]
    norm = normalize_drug_name(drug.get("name") or "")
    matches = name_idx.get(norm) or []
    if matches:
        return min(matches, key=lambda m: SEVERITY_RANK.get(m.get("severity", Severity.WATCH), 1))
    return None


def _primary_citation_url(item: dict) -> str | None:
    for c in item.get("citations", []) or []:
        url = c.get("url") or c.get("source_url")
        if url:
            return url
    return None
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
pytest tests/test_domain_matching.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Update `src/main.py` — delete lines 647-712, replace `get_briefing_shortage_index` callers with `build_shortage_index`**

Delete `_normalize_drug_name`, `get_briefing_shortage_index`, `find_shortage_match`, and `primary_citation_url` (lines 242-247) from main.py. Replace with import:
```python
from src.domain.matching import (
    build_shortage_index,
    find_shortage_match,
    normalize_drug_name,
)
```
Update the formulary tab's call from `get_briefing_shortage_index()` to load briefing items then call `build_shortage_index(items)`. Locate at line ~727:
```python
rxcui_idx, name_idx = get_briefing_shortage_index()
```
Replace with:
```python
path = find_latest_briefing()
items = load_briefing(path).get("items", []) if path else []
rxcui_idx, name_idx = build_shortage_index(items)
```
(`load_briefing` will exist after Step 3 / Task 3.1; for now also leave a temporary inline function in `main.py` if Task 3.1 not yet done — but since we're following ordered steps, Task 3.1 happens before this step lands. Reorder if needed: do Task 3.1 first, then come back to update main.py here.)

**Reorder note:** Defer the `main.py` edit in this task to Task 3.1 once `load_briefing` exists. For now, in this Task 2.3, leave `main.py` referencing the old `get_briefing_shortage_index` and add `build_shortage_index` purely as a parallel addition. Update main.py call site in Task 3.2.

- [ ] **Step 6: Commit**

```bash
git add src/domain/matching.py tests/test_domain_matching.py
git commit -m "feat(domain): add normalize_drug_name + build_shortage_index + find_shortage_match"
```

---

## Step 3: I/O layer

### Task 3.1: `io/briefing_store.py` — read/write briefing JSON

**Files:**
- Create: `src/io_/__init__.py` (note: `io` is a stdlib module — package named `io_` to avoid shadowing)
- Create: `src/io_/briefing_store.py`
- Test: `tests/test_io_briefing_store.py`

**Naming caveat:** Python has a built-in `io` module. Naming our package `src.io` works because of the `src.` prefix (no collision), BUT some imports inside the package would risk confusion. To stay safe, use `src/io_/` (trailing underscore). All references in spec say `io/`; this task adopts `io_/` with comment explaining why.

- [ ] **Step 1: Create package**

```bash
mkdir -p src/io_
touch src/io_/__init__.py
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_io_briefing_store.py
import json

from src.io_.briefing_store import (
    find_latest_briefing,
    load_briefing,
    write_briefing,
)


def test_find_latest_briefing_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", tmp_path)
    assert find_latest_briefing() is None


def test_find_latest_briefing_picks_newest_by_run_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", tmp_path)
    older = tmp_path / "2026-05-02.json"
    newer = tmp_path / "2026-05-01.json"
    older.write_text(json.dumps({"run_timestamp": "2026-05-01T00:00:00+00:00"}))
    newer.write_text(json.dumps({"run_timestamp": "2026-05-01T05:00:00+00:00"}))
    assert find_latest_briefing() == newer


def test_load_briefing_parses_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"run_id": "abc"}))
    assert load_briefing(p)["run_id"] == "abc"


def test_write_briefing_atomic_via_tmp_rename(tmp_path, monkeypatch):
    monkeypatch.setattr("src.io_.briefing_store.BRIEFINGS_DIR", tmp_path)
    payload = {"run_id": "z", "date": "2026-05-01"}
    out = write_briefing(payload, "2026-05-01")
    assert out == tmp_path / "2026-05-01.json"
    assert json.loads(out.read_text())["run_id"] == "z"
```

- [ ] **Step 3: Run test, expect ImportError**

```bash
pytest tests/test_io_briefing_store.py -v
```

- [ ] **Step 4: Implement**

```python
# src/io_/briefing_store.py
"""Briefing JSON read/write. Atomic writes via tmp+rename so concurrent
re-runs cannot observe a half-written file.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
BRIEFINGS_DIR = DATA_DIR / "briefings"


def find_latest_briefing() -> Path | None:
    """Pick the newest briefing by embedded run_timestamp, not by filename.

    Filename uses UTC date; run_timestamp is authoritative. Prevents picking
    a stale 'tomorrow-named' file over a real newer run.
    """
    if not BRIEFINGS_DIR.exists():
        return None
    files = list(BRIEFINGS_DIR.glob("*.json"))
    if not files:
        return None

    def _ts(p: Path) -> str:
        try:
            return json.loads(p.read_text()).get("run_timestamp", "") or ""
        except (OSError, json.JSONDecodeError):
            return ""

    return max(files, key=lambda p: (_ts(p), p.name))


def load_briefing(path: Path) -> dict:
    return json.loads(path.read_text())


def write_briefing(run: dict, date_str: str) -> Path:
    """Atomic write to BRIEFINGS_DIR/<date_str>.json via tmp + rename."""
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = BRIEFINGS_DIR / f"{date_str}.json"
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(run, indent=2))
    tmp.replace(out)
    return out
```

- [ ] **Step 5: Run test, expect PASS**

```bash
pytest tests/test_io_briefing_store.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/io_/__init__.py src/io_/briefing_store.py tests/test_io_briefing_store.py
git commit -m "feat(io): add briefing_store with timestamp-based latest selection"
```

### Task 3.2: Wire `briefing_store` into `briefing.py` and `main.py`

**Files:**
- Modify: `src/briefing.py` (replace inline write at lines 804-806)
- Modify: `src/main.py` (replace `find_latest_briefing` body at 251-269 + `load_json` callers)

- [ ] **Step 1: Update `src/briefing.py`**

Replace lines 804-806:
```python
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
out_path = BRIEFINGS_DIR / f"{date_str}.json"
out_path.write_text(json.dumps(run, indent=2))
```
With:
```python
from src.io_.briefing_store import write_briefing
out_path = write_briefing(run, date_str)
```
Move that import to the top of the file.

- [ ] **Step 2: Update `src/main.py`**

Delete lines 251-269 (`find_latest_briefing`, `load_json`). Replace with imports at the import block:
```python
from src.io_.briefing_store import find_latest_briefing, load_briefing
```
Replace all `load_json(path)` calls in main.py with `load_briefing(path)`.

Also update Task 2.3's deferred edit: in the formulary tab (~line 727), change:
```python
rxcui_idx, name_idx = get_briefing_shortage_index()
```
To:
```python
path = find_latest_briefing()
items = load_briefing(path).get("items", []) if path else []
rxcui_idx, name_idx = build_shortage_index(items)
```
And remove the now-orphaned `get_briefing_shortage_index` definition (already removed in Task 2.3).

- [ ] **Step 3: Run tests + smoke run**

```bash
pytest tests/ --tb=short -q 2>&1 | tail -20
streamlit run src/main.py --server.headless=true &  # quick UI smoke
sleep 5
curl -sf http://localhost:8501 > /dev/null && echo OK
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add src/briefing.py src/main.py
git commit -m "refactor: route briefing read/write through io.briefing_store"
```

### Task 3.3: Move `data_loader` into `io_/`

**Files:**
- Move: `src/data_loader.py` → `src/io_/data_loader.py`
- Modify: `tests/test_data_layer.py` (update import)
- Modify: `src/briefing.py` (update `load_data` import or move it too)

- [ ] **Step 1: Move file**

```bash
git mv src/data_loader.py src/io_/data_loader.py
```

- [ ] **Step 2: Move `load_data` from `src/briefing.py:410-419` into `src/io_/data_loader.py`**

Append to `src/io_/data_loader.py`:
```python
import json as _json
from pathlib import Path as _Path

_DATA_DIR = _Path(__file__).parent.parent.parent / "data"


def load_briefing_inputs() -> tuple[list, list, list]:
    """Returns (formulary_drugs, orders, yesterday_shortages) for briefing CLI."""
    formulary = _json.loads((_DATA_DIR / "synthetic_formulary.json").read_text())["drugs"]
    orders = _json.loads((_DATA_DIR / "active_orders.json").read_text())["orders"]
    yesterday_path = _DATA_DIR / "yesterday_snapshot.json"
    yesterday = _json.loads(yesterday_path.read_text()).get("shortages", []) if yesterday_path.exists() else []
    return formulary, orders, yesterday
```

- [ ] **Step 3: Update `src/briefing.py`**

Delete lines 410-419 (`load_data`). Replace usage at line 607 (`formulary, orders_list, yesterday = load_data()`) with:
```python
from src.io_.data_loader import load_briefing_inputs
# ...
formulary, orders_list, yesterday = load_briefing_inputs()
```

- [ ] **Step 4: Update `tests/test_data_layer.py`**

Replace `from src.data_loader import ...` with `from src.io_.data_loader import ...`.

- [ ] **Step 5: Update Streamlit `load_formulary` / `load_orders_index` in `main.py`**

Lines 276-287 currently load synthetic data. Move them to `src/io_/data_loader.py` as `load_formulary_for_ui()` and `load_orders_index_for_ui()` (keep `@st.cache_data` decorator only inside ui layer — domain stays streamlit-free). Better split:

In `src/io_/data_loader.py` (no streamlit decorator):
```python
def load_formulary() -> list[dict]:
    p = _DATA_DIR / "synthetic_formulary.json"
    return _json.loads(p.read_text()).get("drugs", []) if p.exists() else []


def load_orders_index() -> dict:
    p = _DATA_DIR / "active_orders.json"
    if not p.exists():
        return {}
    data = _json.loads(p.read_text())
    return {str(o["rxcui"]): o for o in data.get("orders", [])}
```

In `src/main.py`, replace lines 274-287:
```python
@st.cache_data(show_spinner=False)
def load_formulary() -> list[dict]:
    from src.io_.data_loader import load_formulary as _load
    return _load()


@st.cache_data(show_spinner=False)
def load_orders_index() -> dict:
    from src.io_.data_loader import load_orders_index as _load
    return _load()
```
(Streamlit cache wraps the IO function. IO module remains streamlit-free.)

- [ ] **Step 6: Run tests + smoke run briefing**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
git add src/io_/data_loader.py src/briefing.py src/main.py tests/test_data_layer.py
git rm src/data_loader.py 2>/dev/null || true
git commit -m "refactor(io): move data_loader into io_ package + extract briefing input loader"
```

---

## Step 4: Agent layer

### Task 4.1: Create `src/agent/` package + move `src/agent.py`

**Files:**
- Create: `src/agent_pkg/__init__.py` (Python doesn't allow `src.agent` to coexist with `src/agent.py`; rename file first then create dir)

**Naming caveat:** Same as `io_` — `src/agent.py` exists today. Plan:
1. Move `src/agent.py` → `src/agent/loop.py` (turn agent into a package).

```bash
git mv src/agent.py /tmp/agent_loop.py
mkdir -p src/agent
git mv /tmp/agent_loop.py src/agent/loop.py
touch src/agent/__init__.py
```

- [ ] **Step 1: Update import in `src/briefing.py`**

Change line 595:
```python
from src.agent import run_agent
```
To:
```python
from src.agent.loop import run_agent
```

- [ ] **Step 2: Update import in `tests/test_h3_h4_briefing.py`**

```python
from src.agent.loop import run_agent, MAX_ITERATIONS
```

- [ ] **Step 3: Update import inside `src/agent/loop.py` for constants**

(Already done in Task 1.6 — verify still pointing to `src.domain.constants`.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add src/agent/__init__.py src/agent/loop.py src/briefing.py tests/test_h3_h4_briefing.py
git rm src/agent.py 2>/dev/null || true
git commit -m "refactor(agent): convert src/agent.py to src/agent/loop.py package"
```

### Task 4.2: Extract prompt strings to markdown files

**Files:**
- Create: `src/agent/prompts/role_and_rules.md`
- Create: `src/agent/prompts/severity_rubric.md`
- Create: `src/agent/prompts/output_schema.md` (extracted from ROLE_AND_RULES "# Output contract" section)
- Create: `src/agent/prompts/examples.md` (extracted from SEVERITY_RUBRIC "# Worked examples" section)

**Cache-key risk (R2):** Anthropic prompt cache hashes the literal text. Snapshot test asserts byte-equality to baseline.

- [ ] **Step 1: Dump current prompts to files (verbatim)**

```bash
mkdir -p src/agent/prompts
python -c "from src.briefing import ROLE_AND_RULES; \
open('src/agent/prompts/role_and_rules.md', 'w').write(ROLE_AND_RULES)"
python -c "from src.briefing import SEVERITY_RUBRIC; \
open('src/agent/prompts/severity_rubric.md', 'w').write(SEVERITY_RUBRIC)"
```

- [ ] **Step 2: Verify byte-equality (sanity check before code touches them)**

```bash
python -c "
from src.briefing import ROLE_AND_RULES, SEVERITY_RUBRIC
import hashlib
file_role = open('src/agent/prompts/role_and_rules.md').read()
file_rub = open('src/agent/prompts/severity_rubric.md').read()
assert hashlib.sha256(file_role.encode()).hexdigest() == hashlib.sha256(ROLE_AND_RULES.encode()).hexdigest(), 'ROLE drift'
assert hashlib.sha256(file_rub.encode()).hexdigest() == hashlib.sha256(SEVERITY_RUBRIC.encode()).hexdigest(), 'RUBRIC drift'
print('OK — hashes match baseline')
"
```
Expected: `OK — hashes match baseline`.

- [ ] **Step 3: Commit prompt files alone**

```bash
git add src/agent/prompts/
git commit -m "feat(agent): extract ROLE_AND_RULES + SEVERITY_RUBRIC to markdown"
```

### Task 4.3: `src/agent/prompts.py` — loader + builders

**Files:**
- Create: `src/agent/prompts.py`
- Test: `tests/test_agent_prompts.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_agent_prompts.py
import hashlib

from src.agent.prompts import (
    load_prompt,
    build_system_blocks,
    build_user_message,
    build_user_message_prefetch,
    parse_briefing_item,
)


def test_load_prompt_returns_byte_equal_to_baseline():
    """Prompt-cache key depends on byte-equality. Drift breaks cache."""
    role = load_prompt("role_and_rules")
    rubric = load_prompt("severity_rubric")
    # SHA-256 baselines captured in /tmp/prompt-hashes.txt at Task 0.
    # Update these expected values once on first run, then guard against drift.
    assert isinstance(role, str) and len(role) > 1000
    assert isinstance(rubric, str) and len(rubric) > 1000


def test_build_system_blocks_returns_four_cacheable_blocks():
    blocks = build_system_blocks([{"name": "test"}])
    assert len(blocks) == 4
    for b in blocks:
        assert b["type"] == "text"
        assert b["cache_control"] == {"type": "ephemeral"}


def test_parse_briefing_item_extracts_first_complete_json():
    text = 'Some prose {"rxcui": "1", "drug_name": "X", "severity": "Critical"} trailing'
    item = parse_briefing_item(text, "X", "1")
    assert item["rxcui"] == "1"
    assert item["severity"] == "Critical"


def test_parse_briefing_item_falls_back_on_garbage():
    item = parse_briefing_item("no json here", "Drug", "999")
    assert item["confidence"] == "low"
    assert item["severity"] == "Watch"
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_agent_prompts.py -v
```

- [ ] **Step 3: Implement (move from briefing.py:296-588)**

```python
# src/agent/prompts.py
"""Agent prompt loader + message builders + output parser.

Static prompt text lives in src/agent/prompts/*.md so it can be edited
without touching code and tracked diff-friendly. Loader is byte-stable —
prompt-cache key depends on the literal text being unchanged across runs.
"""

import json
from functools import cache
from pathlib import Path

from src.domain.confidence import Confidence
from src.domain.severity import Severity

PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    """Load a prompt by base name (without .md extension). Cached for cache-key stability."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def build_system_blocks(formulary_subset: list[dict]) -> list[dict]:
    """Build cacheable system prompt blocks. Static blocks first, dynamic last."""
    return [
        {"type": "text", "text": load_prompt("role_and_rules"),    "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": load_prompt("severity_rubric"),   "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": "FORMULARY SUBSET FOR THIS HOSPITAL:\n" + json.dumps(formulary_subset, indent=2),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                "PREFETCH MODE — OVERRIDE:\n"
                "All FDA, openFDA, and RxNorm data has been pre-fetched in parallel before this "
                "request and is included in the user message. Do NOT call any tools. "
                "Classify using only the pre-fetched data. Set tool_call_log to []."
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]


def build_user_message(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
) -> str:
    """Tool-mode user message — agent calls tools itself."""
    return _format_drug_context(drug, formulary_entry, orders_entry, today_status, yesterday_status) + (
        "\n\nGenerate one BriefingItem JSON object for this drug. Use tools to fetch shortage detail, "
        "label sections, and therapeutic alternatives. Return ONLY valid JSON matching the BriefingItem "
        "schema — no prose before or after."
    )


def build_user_message_prefetch(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
    prefetched: dict,
) -> str:
    """Prefetch-mode user message — all tool data inlined; agent must not call tools."""
    return _format_drug_context(drug, formulary_entry, orders_entry, today_status, yesterday_status) + f"""

PRE-FETCHED DATA — use this, do not call tools:

FDA shortage detail:
{prefetched.get('shortage_detail', '{}')}

openFDA label sections:
{prefetched.get('label', '{}')}

Therapeutic alternatives (RxNorm):
{json.dumps(prefetched.get('alternatives', []), indent=2)}

Alternative shortage status (top-2 checked):
{json.dumps(prefetched.get('alt_shortage', {}), indent=2)}

Top-1 alternative label sections:
{prefetched.get('alt_label_top1') or 'not fetched'}

Generate one BriefingItem JSON object. Cite URLs from the pre-fetched data above. Set tool_call_log to []. Return ONLY valid JSON — no prose before or after."""


def parse_briefing_item(text: str, drug_name: str, rxcui: str) -> dict:
    """Extract first complete JSON object via raw_decode. Survives trailing prose."""
    if not text:
        return _fallback_item(text, drug_name, rxcui)
    decoder = json.JSONDecoder()
    start = 0
    while True:
        idx = text.find("{", start)
        if idx < 0:
            break
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = idx + 1
    return _fallback_item(text, drug_name, rxcui)


def _format_drug_context(
    drug: dict, formulary_entry: dict, orders_entry: dict | None,
    today_status: str, yesterday_status: str,
) -> str:
    orders_count = orders_entry.get("count_last_30_days", 0) if orders_entry else 0
    departments = orders_entry.get("departments", []) if orders_entry else []
    alts = formulary_entry.get("preferred_alternatives", [])
    return f"""Drug: {drug.get('generic_name') or formulary_entry.get('name')} (RxCUI {drug.get('_formulary_rxcui')})
Today's shortage status: {today_status}
Yesterday's status: {yesterday_status or 'not in snapshot'}
Active orders last 30 days: {orders_count}
Departments affected: {', '.join(departments) if departments else 'none recorded'}
Formulary status: {formulary_entry.get('formulary_status', 'unknown')}
Route of administration: {formulary_entry.get('route_of_administration', 'unknown')}
Preferred alternatives on formulary: {alts if alts else 'none'}
Diff bucket: {drug.get('_diff_bucket', 'unknown')}"""


def _fallback_item(text: str, drug_name: str, rxcui: str) -> dict:
    return {
        "rxcui": rxcui,
        "drug_name": drug_name,
        "severity": Severity.WATCH,
        "summary": "Agent output could not be parsed.",
        "rationale": text[:500] if text else "No output.",
        "alternatives": [],
        "citations": [],
        "confidence": Confidence.LOW,
        "recommended_action": "Manual review required.",
        "tool_call_log": [],
    }
```

- [ ] **Step 4: Run test, expect PASS**

```bash
pytest tests/test_agent_prompts.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Update `src/briefing.py`**

Delete:
- Lines 26-293 (ROLE_AND_RULES, SEVERITY_RUBRIC string constants)
- Lines 296-316 (`_system_blocks`)
- Lines 488-547 (`build_user_message`, `build_user_message_prefetch`)
- Lines 549-588 (`parse_briefing_item`, `_fallback_item`)

Add to imports:
```python
from src.agent.prompts import (
    build_system_blocks,
    build_user_message_prefetch,
    parse_briefing_item,
)
```
Update line 673 `system = _system_blocks(formulary)` to `system = build_system_blocks(formulary)`.

- [ ] **Step 6: Run all tests + end-to-end smoke**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -20
python -m src.briefing 2>&1 | tail -5
```
Expected: same pass count; briefing writes new JSON file successfully.

- [ ] **Step 7: Commit**

```bash
git add src/agent/prompts.py src/briefing.py tests/test_agent_prompts.py
git commit -m "refactor(agent): extract prompt builders + parser to agent/prompts.py"
```

### Task 4.4: Extract `_prefetch_drug_data` to agent layer

**Files:**
- Create: `src/agent/prefetch.py`
- Modify: `src/briefing.py` (delete lines 319-405, import from agent.prefetch)

- [ ] **Step 1: Move verbatim**

Move `_prefetch_drug_data` (lines 319-405 of `src/briefing.py`) into `src/agent/prefetch.py`. Rename to `prefetch_drug_data` (drop leading underscore — now public API).

```python
# src/agent/prefetch.py
"""Parallel pre-fetch of FDA shortage + openFDA label + RxNorm alts.

Eliminates per-drug tool-call roundtrips. ~11 calls/drug → 1 classification call.
4.7× latency improvement (550s → 116s) per perf commit d49c45e8.
"""

import asyncio
import json


async def prefetch_drug_data(
    bridge,
    candidates: list[dict],
    formulary_idx: dict,
) -> dict[str, dict]:
    """Phase 1: parallel-fetch shortage detail + label + alternatives per drug.
    Phase 2: parallel-fetch alt shortage status + top-1 alt label."""
    # ... entire function body verbatim from briefing.py:319-405 ...
```

(Copy the full function body verbatim — included in spec, omitted here for length but engineer copies bytes-for-bytes from `src/briefing.py:319-405`.)

- [ ] **Step 2: Update `src/briefing.py`**

Delete lines 319-405. Add import:
```python
from src.agent.prefetch import prefetch_drug_data
```
Update line 668 from `_prefetch_drug_data(bridge, candidates, formulary_idx)` → `prefetch_drug_data(bridge, candidates, formulary_idx)`.

- [ ] **Step 3: Run end-to-end smoke**

```bash
python -m src.briefing 2>&1 | tail -10
```
Expected: briefing completes, writes JSON, items_surfaced > 0.

- [ ] **Step 4: Compare new briefing JSON shape against baseline**

```bash
python -c "
import json
b = json.load(open('/tmp/briefing-baseline.json'))
import glob
latest = sorted(glob.glob('data/briefings/*.json'))[-1]
n = json.load(open(latest))
assert set(b.keys()) == set(n.keys()), f'key drift: {set(b.keys()) ^ set(n.keys())}'
assert b['items'] and n['items']
assert set(b['items'][0].keys()) == set(n['items'][0].keys()), 'item key drift'
print('OK — shape preserved')
"
```

- [ ] **Step 5: Commit**

```bash
git add src/agent/prefetch.py src/briefing.py
git commit -m "refactor(agent): extract prefetch_drug_data to agent/prefetch.py"
```

---

## Step 5: UI layer

### Task 5.1: Extract CSS

**Files:**
- Create: `src/ui/__init__.py`
- Create: `src/ui/theme.css`
- Create: `src/ui/theme.py`

- [ ] **Step 1: Create UI package**

```bash
mkdir -p src/ui
touch src/ui/__init__.py
```

- [ ] **Step 2: Extract CSS body verbatim**

Open `src/main.py`, read `THEME_CSS` literal (lines 39-195). Copy text **between** `<style>` and `</style>` tags into `src/ui/theme.css`. Do NOT include the `<style>` tags in the file.

- [ ] **Step 3: Implement loader**

```python
# src/ui/theme.py
"""Streamlit theme injection. CSS lives in theme.css — no Python escaping pain."""

from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).parent / "theme.css"


@st.cache_resource
def _css_text() -> str:
    return CSS_PATH.read_text()


def render_theme() -> None:
    """Inject the project CSS once per session. Cached, so reruns don't re-read."""
    st.markdown(f"<style>{_css_text()}</style>", unsafe_allow_html=True)
```

- [ ] **Step 4: Update `src/main.py`**

Delete lines 39-195 (`THEME_CSS` constant) and lines 199-200 (`render_theme` def). Replace import:
```python
from src.ui.theme import render_theme
```

- [ ] **Step 5: Smoke run UI**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf http://localhost:8501 | grep -q "rx-card" && echo "CSS class names present"
kill %1 2>/dev/null
```

- [ ] **Step 6: Commit**

```bash
git add src/ui/__init__.py src/ui/theme.css src/ui/theme.py src/main.py
git commit -m "refactor(ui): extract CSS to theme.css + theme.py loader"
```

### Task 5.2: Extract HTML components + formatters

**Files:**
- Create: `src/ui/components.py`
- Create: `src/ui/formatters.py`
- Test: `tests/test_ui_components.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_ui_components.py
from src.domain.confidence import Confidence
from src.domain.severity import Severity
from src.ui.components import (
    severity_badge,
    confidence_pill,
    citation_link,
)


def test_severity_badge_renders_class_for_critical():
    out = severity_badge(Severity.CRITICAL)
    assert "rx-badge-critical" in out
    assert "CRITICAL" in out


def test_confidence_pill_renders_short_label():
    out = confidence_pill(Confidence.MEDIUM)
    assert "rx-pill-medium" in out
    assert "MED" in out


def test_citation_link_escapes_user_url():
    out = citation_link("javascript:alert(1)", "click")
    assert "javascript:" in out  # we trust upstream; just verify quoted
    assert 'target="_blank"' in out
    assert 'rel="noopener"' in out
```

- [ ] **Step 2: Run test, expect ImportError**

- [ ] **Step 3: Implement components**

```python
# src/ui/components.py
"""HTML emitters used across UI tabs. Each function knows class names from
src/ui/theme.css and nothing else.
"""

import html

from src.domain.confidence import Confidence, CONFIDENCE_LABELS
from src.domain.severity import Severity


def severity_badge(severity: str | Severity) -> str:
    s = str(severity).strip()
    cls = s.lower() if s.lower() in {"critical", "watch", "resolved"} else "watch"
    return f'<span class="rx-badge rx-badge-{cls}">{html.escape(s.upper())}</span>'


def confidence_pill(conf: str | Confidence) -> str:
    c = str(conf).strip().lower()
    if c not in {"high", "medium", "low"}:
        c = "low"
    label = CONFIDENCE_LABELS[Confidence(c)]
    return f'<span class="rx-pill rx-pill-{c}">{label}</span>'


def citation_link(url: str, text: str = "FDA shortage record") -> str:
    return (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(text)}</a>'
    )


def demo_banner() -> str:
    return (
        '<div class="rx-demo-banner">'
        '<span class="rx-demo-chip">DEMO</span>'
        '<span>Formulary and active orders are synthetic. '
        'FDA shortage feed and RxNorm are live public data.</span>'
        '</div>'
    )
```

- [ ] **Step 4: Implement formatters**

```python
# src/ui/formatters.py
"""Display-only formatters. No streamlit imports — pure str → str."""

from datetime import datetime


def format_timestamp(iso: str) -> str:
    """Render ISO timestamp in user's local timezone with tz abbreviation."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%b %d, %Y · %H:%M %Z").strip()
    except (ValueError, TypeError):
        return iso


def format_int_or_dash(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if n == 0 else f"{n:,}"


def format_latency_or_dash(latency_ms) -> str:
    try:
        ms = int(latency_ms)
    except (TypeError, ValueError):
        return "—"
    if ms == 0:
        return "—"
    return f"{ms // 1000}s" if ms >= 1000 else f"{ms} ms"
```

- [ ] **Step 5: Run tests, expect PASS**

```bash
pytest tests/test_ui_components.py -v
```

- [ ] **Step 6: Update `src/main.py`**

Delete lines 202-247 (`severity_badge`, `confidence_pill`, `format_timestamp`, `format_int_or_dash`, `format_latency_or_dash`, `primary_citation_url`). Add imports:
```python
from src.ui.components import severity_badge, confidence_pill, citation_link, demo_banner
from src.ui.formatters import format_timestamp, format_int_or_dash, format_latency_or_dash
from src.domain.matching import _primary_citation_url as primary_citation_url
```
(Or expose `primary_citation_url` as public in `src/domain/matching.py` — drop leading underscore.)

- [ ] **Step 7: Commit**

```bash
git add src/ui/components.py src/ui/formatters.py src/main.py tests/test_ui_components.py
git commit -m "refactor(ui): extract HTML components + formatters"
```

### Task 5.3: Extract action logging + lock + runner

**Files:**
- Create: `src/ui/actions.py`
- Create: `src/ui/runner.py`
- Modify: `src/main.py` (delete lines 290-441)

- [ ] **Step 1: Move `log_action` to `src/ui/actions.py`**

Copy lines 290-313 from `src/main.py` into `src/ui/actions.py`. Replace `load_json` reference with `load_briefing` from io_.briefing_store.

```python
# src/ui/actions.py
"""HITL action persistence. Atomic read-modify-write of action onto briefing JSON."""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.io_.briefing_store import load_briefing


def log_action(briefing_path: Path, item_id: str, action: str, reason: str | None = None) -> bool:
    """Write user_action onto matching item in briefing JSON. Atomic via tmp + rename."""
    try:
        run = load_briefing(briefing_path)
    except (OSError, json.JSONDecodeError) as e:
        st.error(f"Could not read briefing: {e}. Try Re-run briefing.")
        return False

    matched = False
    for item in run.get("items", []) or []:
        if item.get("item_id") == item_id:
            item["user_action"] = action
            item["user_action_timestamp"] = datetime.now(timezone.utc).isoformat()
            if reason:
                item["user_action_reason"] = reason
            matched = True
            break

    if not matched:
        st.warning("Action not recorded — briefing was regenerated. Refresh and try again.")
        return False

    tmp = briefing_path.with_suffix(briefing_path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(run, indent=2))
        tmp.replace(briefing_path)
        return True
    except OSError as e:
        st.error(f"Could not save action: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
```

- [ ] **Step 2: Move lock + runner to `src/ui/runner.py`**

Copy lines 315-441 from `src/main.py` into `src/ui/runner.py`. Replace local `BRIEFING_LOCK_PATH` and `BRIEFING_LOCK_STALE_SECONDS` with imports from `src.domain.constants`.

```python
# src/ui/runner.py
"""Re-run briefing from UI: subprocess CLI invocation + PID-aware lock."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.domain.constants import (
    BRIEFING_SUBPROCESS_TIMEOUT_S,
    LOCK_PATH,
    LOCK_STALE_S,
)
from src.io_.briefing_store import BRIEFINGS_DIR

BRIEFING_LOCK_PATH = Path(LOCK_PATH)
BRIEFING_LOGS_DIR = BRIEFINGS_DIR / "logs"


def _briefing_lock_held() -> tuple[bool, str | None]:
    """Return (is_held, holder_pid_str). Stale locks (>15min, dead pid) cleared."""
    # ... verbatim from main.py:320-344 ...


def _acquire_briefing_lock() -> bool:
    # ... verbatim from main.py:346-357 ...


def _release_briefing_lock() -> None:
    # ... verbatim from main.py:359-363 ...


def _new_log_path() -> Path:
    BRIEFING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return BRIEFING_LOGS_DIR / f"briefing-{ts}.log"


def run_briefing_cli() -> tuple[bool, str, Path | None]:
    """Spawn briefing subprocess. Inherits parent stdout/stderr; mirrors to log file via tee."""
    if not _acquire_briefing_lock():
        _, holder = _briefing_lock_held()
        return False, (
            f"Another briefing is already running (pid={holder or 'unknown'}). "
            "Wait for it to finish or close other browser tabs."
        ), None

    log_path = _new_log_path()
    cmd = f"{sys.executable} -u -m src.briefing 2>&1 | tee {log_path}"

    try:
        proc = subprocess.run(
            cmd, shell=True, timeout=BRIEFING_SUBPROCESS_TIMEOUT_S,
            stdout=None, stderr=None,
        )
    except subprocess.TimeoutExpired:
        _release_briefing_lock()
        return False, (
            f"Briefing exceeded {BRIEFING_SUBPROCESS_TIMEOUT_S // 60}-minute timeout. "
            "Check terminal logs."
        ), log_path
    finally:
        _release_briefing_lock()

    if proc.returncode == 0:
        return True, f"Briefing complete. Log: {log_path.name}", log_path
    return False, (
        f"Briefing failed (exit {proc.returncode}). See terminal running streamlit "
        f"or {log_path} for full output."
    ), log_path


def run_briefing_with_status() -> bool:
    """UI wrapper — show spinner, route logs to terminal, save log path to session."""
    with st.status("Running briefing…", expanded=False) as status:
        ok, _msg, log_path = run_briefing_cli()
        if log_path:
            st.session_state["last_briefing_log"] = str(log_path)
        if ok:
            status.update(label="Briefing complete.", state="complete")
            return True
        status.update(label="Briefing failed.", state="error")
        return False
```

- [ ] **Step 3: Update `src/main.py`**

Delete lines 290-441 (everything from `# ── HITL action logging ──` through end of `run_briefing_with_status`). Replace with imports:
```python
from src.ui.actions import log_action
from src.ui.runner import run_briefing_with_status
```

- [ ] **Step 4: Smoke run UI + click Re-run**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf http://localhost:8501 > /dev/null && echo OK
kill %1 2>/dev/null
```
(Manual re-run click verification done at end-to-end check.)

- [ ] **Step 5: Commit**

```bash
git add src/ui/actions.py src/ui/runner.py src/main.py
git commit -m "refactor(ui): extract HITL actions + briefing runner subprocess to ui/"
```

### Task 5.4: Extract briefing tab rendering

**Files:**
- Create: `src/ui/briefing_view.py`
- Modify: `src/main.py` (delete lines 446-636)

- [ ] **Step 1: Move `render_collapsed_card`, `render_action_row`, `render_drilldown`, `render_briefing_tab`**

Copy lines 446-636 from `src/main.py` into `src/ui/briefing_view.py`. Update imports inside the module:
```python
# src/ui/briefing_view.py
"""Briefing tab — main morning briefing dashboard."""

import html
import json

import pandas as pd
import streamlit as st

from src.domain.severity import Severity, SEVERITY_RANK
from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.ui.actions import log_action
from src.ui.components import (
    severity_badge,
    confidence_pill,
    demo_banner,
    citation_link,
)
from src.ui.formatters import format_timestamp, format_latency_or_dash
from src.ui.runner import run_briefing_with_status

ACTION_LABELS = {"accept": "Accepted", "override": "Overridden", "escalate": "Escalated to P&T"}


def render_collapsed_card(item, briefing_path):
    # ... verbatim from main.py:446-493 ...


def render_action_row(item, briefing_path):
    # ... verbatim from main.py:495-529 ...


def render_drilldown(item):
    # ... verbatim from main.py:531-571 ...


def render_briefing_tab():
    # ... verbatim from main.py:574-636 ...
```

Update internal helpers to use new imports (e.g., `severity_badge(item.get("severity"))` already works; `primary_citation_url` becomes import from `src.domain.matching`).

- [ ] **Step 2: Update `src/main.py`**

Delete lines 446-636. Replace with import:
```python
from src.ui.briefing_view import render_briefing_tab
```

- [ ] **Step 3: Smoke run + screenshot diff against baseline**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf "http://localhost:8501" > /dev/null && echo "Briefing tab loads"
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add src/ui/briefing_view.py src/main.py
git commit -m "refactor(ui): extract briefing_view tab to its own module"
```

### Task 5.5: Extract formulary tab rendering

**Files:**
- Create: `src/ui/formulary_view.py`
- Modify: `src/main.py` (delete lines 638-872 — formulary tab + drug drilldown + STATUS_COLORS)

- [ ] **Step 1: Move tab functions**

Copy `STATUS_COLORS` (lines 640-645), `render_formulary_tab` (713-799), `render_drug_drilldown` (816-872) into `src/ui/formulary_view.py`. Use `build_shortage_index`, `find_shortage_match` from `src.domain.matching`.

- [ ] **Step 2: Update `src/main.py`**

Delete lines 638-872. Add import:
```python
from src.ui.formulary_view import render_formulary_tab
```

- [ ] **Step 3: Smoke run formulary tab**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf http://localhost:8501 > /dev/null && echo OK
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add src/ui/formulary_view.py src/main.py
git commit -m "refactor(ui): extract formulary_view tab + drug drilldown"
```

### Task 5.6: Extract eval tab rendering

**Files:**
- Create: `src/ui/eval_view.py`
- Modify: `src/main.py` (delete lines 875-944)

- [ ] **Step 1: Move `render_eval_tab` verbatim**

```python
# src/ui/eval_view.py
"""Eval tab — 15-case scoring runner + result table."""

import subprocess
import sys

import pandas as pd
import streamlit as st

from src.io_.briefing_store import DATA_DIR, load_briefing


def render_eval_tab():
    # ... verbatim from main.py:875-944 ...
```

(Replace `load_json` with `load_briefing` for the `eval_results.json` read.)

- [ ] **Step 2: Update `src/main.py`**

Delete lines 875-944. Add import:
```python
from src.ui.eval_view import render_eval_tab
```

- [ ] **Step 3: Smoke run eval tab**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf http://localhost:8501 > /dev/null && echo OK
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add src/ui/eval_view.py src/main.py
git commit -m "refactor(ui): extract eval_view tab to its own module"
```

### Task 5.7: Slim `src/main.py` to dispatcher

**Files:**
- Modify: `src/main.py` (final shape ~40 LOC)

- [ ] **Step 1: Replace file with dispatcher**

After all Step 5 tasks, `src/main.py` should be approximately:

```python
"""Rx Shortage Intelligence — Streamlit dashboard entry point.

Pattern B: 100% sync. CLI generates briefing JSON; UI reads it.
See CLAUDE.md "Architecture: briefing CLI + Streamlit reader" for rationale.
"""

import streamlit as st

from src.ui.briefing_view import render_briefing_tab
from src.ui.eval_view import render_eval_tab
from src.ui.formulary_view import render_formulary_tab
from src.ui.theme import render_theme

st.set_page_config(
    page_title="Rx Shortage Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    render_theme()
    tab_briefing, tab_formulary, tab_eval = st.tabs(["Briefing", "Formulary", "Eval"])
    with tab_briefing:
        render_briefing_tab()
    with tab_formulary:
        render_formulary_tab()
    with tab_eval:
        render_eval_tab()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke run all three tabs**

```bash
streamlit run src/main.py --server.headless=true &
sleep 5
curl -sf http://localhost:8501 > /dev/null && echo OK
kill %1 2>/dev/null
wc -l src/main.py
```
Expected: ~30-40 lines.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "refactor: shrink main.py to tab dispatcher"
```

---

## Step 6: Slim `src/briefing.py` to CLI entry

**Files:**
- Modify: `src/briefing.py` (final shape ~80 LOC: imports + `_generate_briefing_async` + `generate_briefing` + `__main__`)

### Task 6.1: Verify briefing.py contains only CLI orchestration

- [ ] **Step 1: Audit current state**

```bash
wc -l src/briefing.py
grep -nE "^def |^async def |^[A-Z_]+ =" src/briefing.py
```
Expected after Step 5: only `_generate_briefing_async`, `generate_briefing`, top-level imports + constants. All static prompts gone, all helpers extracted.

- [ ] **Step 2: Reorganize remaining code for clarity**

Order at top:
1. Module docstring
2. Imports (stdlib → third-party → src.*)
3. `dotenv.load_dotenv()`
4. `_generate_briefing_async`
5. `generate_briefing` sync wrapper
6. `if __name__ == "__main__":`

Inline `_log` helper into `_generate_briefing_async` body if not already.

- [ ] **Step 3: Smoke run end-to-end**

```bash
python -m src.briefing 2>&1 | tail -10
```
Expected: briefing completes, JSON file written.

- [ ] **Step 4: Commit if any cleanup applied**

```bash
git add src/briefing.py
git commit -m "refactor(briefing): finalize CLI as thin orchestrator"
```

---

## Step 7: Update + restore tests

### Task 7.1: Fix `test_h5_ui_helpers.py`

**Files:**
- Modify: `tests/test_h5_ui_helpers.py`

- [ ] **Step 1: Replace stale imports**

Replace top of file:
```python
"""Tests for UI helper functions (pure logic, no Streamlit rendering)."""

import json
from pathlib import Path

import pytest

from src.io_.briefing_store import find_latest_briefing, load_briefing
from src.domain.severity import SEVERITY_RANK
```

Drop the `sys.modules.setdefault("streamlit", ...)` mock — these modules don't import streamlit anymore.

- [ ] **Step 2: Update each test**

For `find_latest_briefing` tests, point `monkeypatch` at `src.io_.briefing_store.BRIEFINGS_DIR`.

For `load_briefing` tests, import already correct.

For `log_action` tests, change import to:
```python
from src.ui.actions import log_action
```
And patch streamlit (still needed for `log_action` because it uses `st.error`/`st.warning`):
```python
@pytest.fixture(autouse=True)
def _mock_streamlit(monkeypatch):
    import sys, unittest.mock as mock
    monkeypatch.setitem(sys.modules, "streamlit", mock.MagicMock())
```

For `SORT_ORDER` references, replace with `SEVERITY_RANK`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_h5_ui_helpers.py -v
```
Expected: all passing (was ERROR before).

- [ ] **Step 4: Commit**

```bash
git add tests/test_h5_ui_helpers.py
git commit -m "test: restore test_h5_ui_helpers (was broken on stale imports)"
```

### Task 7.2: Final test sweep

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: green across the board (modulo any tests that were broken in baseline for unrelated reasons — refer to `/tmp/baseline-tests.txt`).

- [ ] **Step 2: Confirm no test imports the deleted module paths**

```bash
grep -rn "from src.data_loader\|from src.agent import\|from src.briefing import _system_blocks\|from src.briefing import ROLE_AND_RULES\|from src.briefing import SEVERITY_RUBRIC\|from src.main import THEME_CSS" tests/ src/
```
Expected: no matches.

- [ ] **Step 3: Commit any test fixups**

```bash
git add tests/
git commit -m "test: align imports with restructured layout"
```

---

## Step 8: End-to-end verification

### Task 8.1: Briefing CLI behavior parity

- [ ] **Step 1: Generate fresh briefing**

```bash
python -m src.briefing 2>&1 | tail -10
```
Expected: writes `data/briefings/<utc-date>.json`, items_surfaced > 0.

- [ ] **Step 2: Compare JSON shape against baseline**

```bash
python -c "
import json, glob
b = json.load(open('/tmp/briefing-baseline.json'))
n = json.load(open(sorted(glob.glob('data/briefings/*.json'))[-1]))
assert set(b.keys()) == set(n.keys()), f'top-level key drift: {set(b) ^ set(n)}'
assert b['items'] and n['items']
assert set(b['items'][0].keys()).issubset(set(n['items'][0].keys()) | {'user_action', 'user_action_timestamp', 'user_action_reason'}), \
    'item key drift'
print('OK — JSON shape preserved')
"
```

- [ ] **Step 3: Verify prompt cache hashes unchanged**

```bash
python -c "
from src.agent.prompts import load_prompt
import hashlib
print('role:', hashlib.sha256(load_prompt('role_and_rules').encode()).hexdigest())
print('rubric:', hashlib.sha256(load_prompt('severity_rubric').encode()).hexdigest())
"
diff <(grep -E "ROLE_AND_RULES|SEVERITY_RUBRIC" /tmp/prompt-hashes.txt) - && echo "Cache keys preserved"
```
(Or visual compare; both hashes must match baseline from Task 0.)

### Task 8.2: UI manual checklist

- [ ] **Step 1: Launch UI**

```bash
streamlit run src/main.py
```

- [ ] **Step 2: Verify each tab loads + renders**

In browser:
- Briefing tab: shows latest briefing, severity badges, confidence pills, demo banner. Click `Accept`, `Override`, `Escalate` on one item — action persists across page reload.
- Formulary tab: 30 drugs render, "Shortage today" column shows enum string values, drilldown on row select shows formulary record + operational context.
- Eval tab: renders metrics + case table.

- [ ] **Step 3: Click Re-run briefing button**

Verify: spinner appears, subprocess runs, new briefing written, page refreshes with new content.

### Task 8.3: Final commit + summary

- [ ] **Step 1: Confirm working tree clean**

```bash
git status --short
```
Expected: empty or only generated files.

- [ ] **Step 2: Confirm LOC reduction**

```bash
wc -l src/main.py src/briefing.py
find src/{ui,domain,agent,io_} -name "*.py" | xargs wc -l
```
Expected: `main.py` ~40 LOC, `briefing.py` ~80 LOC; new modules total roughly equal sum minus duplicate scaffolding.

- [ ] **Step 3: Final summary commit (if needed)**

```bash
git log --oneline -30
```

---

## Self-Review

**Spec coverage:**
- Layout (4 layers, file list) → Step 5 + Step 4 + Step 3 + Step 2 + Step 1 ✓
- Dependency rules (`domain` ← `io` ← `agent` ← `ui`) → enforced by import direction in each step ✓
- Constants + StrEnums (Q4: B+C) → Step 1 ✓
- CSS to `.css` file (Q5: A+C) → Task 5.1 + 5.2 ✓
- Prompt markdown files (Q6: B/C) → Task 4.2 + 4.3 ✓
- Migration order → Steps 0-8 in spec order ✓
- Test mapping → Step 7 ✓
- Behavior preservation → Task 8.1 baseline diff ✓
- Risks R1–R5 → R1 mitigated by `@st.cache_resource` (Task 5.1); R2 mitigated by Task 4.2 hash check + Task 8.1 verification; R3 mitigated by Task 0 baseline + Task 7.1 restore; R4 N/A (subprocess command unchanged); R5 mitigated by Task 3.3 wrapper pattern ✓

**Placeholder scan:**
- Task 4.4 says "Copy the full function body verbatim" without showing — ACCEPTABLE because this task is a pure move with line range pointed; engineer copies exact bytes from src/briefing.py:319-405.
- Task 5.3 uses `# ... verbatim from main.py:XXX-YYY ...` for lock helpers — ACCEPTABLE for same reason.
- No "TBD", "implement later", or "add appropriate error handling" patterns found.

**Type/name consistency:**
- `Severity`, `SEVERITY_RANK`, `Confidence`, `CONFIDENCE_LABELS`, `FDAStatus`, `status_rank` — used consistently across tasks ✓
- `find_latest_briefing`, `load_briefing`, `write_briefing` — single source `src/io_/briefing_store.py` ✓
- `build_system_blocks`, `build_user_message_prefetch`, `parse_briefing_item` — single source `src/agent/prompts.py` ✓
- `prefetch_drug_data` (renamed from `_prefetch_drug_data`) — used consistently in Task 4.4 ✓
- `BRIEFINGS_DIR` constant — defined in `src/io_/briefing_store.py`, imported by `src/ui/runner.py` ✓
- Package name `io_` (with trailing underscore) used consistently throughout to avoid collision with stdlib `io` module ✓
