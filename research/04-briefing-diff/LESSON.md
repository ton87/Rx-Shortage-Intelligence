# Briefing + Diff Logic — Lesson

## What this layer owns

The orchestration that turns raw FDA data + formulary + yesterday snapshot into a structured BriefingRun. Two main operations:

1. **Diff**: compute what changed between yesterday and today
2. **Severity classify**: bucket each diff item into Critical / Watch / Resolved

Then for each surviving item, the agent loop fetches label chunks, finds alternatives, and produces a BriefingItem. Final result = BriefingRun JSON.

## Diff semantics

Inputs:
- `today_shortages`: list of records from live FDA feed (filtered to those with RxCUI)
- `yesterday_shortages`: list from `data/yesterday_snapshot.json`
- `formulary`: list of drugs we care about (filter: drop anything not on formulary)

Output:
```python
{
    "new": [...],         # in today, not in yesterday  → potentially Critical/Watch
    "escalated": [...],   # in both, but status worsened  → potentially Critical
    "improved": [...],    # in both, but status improved  → typically Watch
    "resolved": [...],    # in yesterday, not in today  → Resolved bucket
    "unchanged": [...],   # in both, same status  → skip (don't re-brief)
}
```

Implementation:

```python
def compute_diff(today: list[dict], yesterday: list[dict], formulary_rxcuis: set[str]) -> dict:
    today_idx = {r["rxcui"]: r for r in today if r["rxcui"] in formulary_rxcuis}
    yest_idx = {r["rxcui"]: r for r in yesterday if r["rxcui"] in formulary_rxcuis}

    today_keys = set(today_idx)
    yest_keys = set(yest_idx)

    new_keys = today_keys - yest_keys
    resolved_keys = yest_keys - today_keys
    overlap = today_keys & yest_keys

    escalated, improved, unchanged = [], [], []
    for k in overlap:
        t_status = today_idx[k]["status"]
        y_status = yest_idx[k]["status"]
        if t_status == y_status:
            unchanged.append(today_idx[k])
        elif _is_worse(t_status, y_status):
            escalated.append(today_idx[k])
        else:
            improved.append(today_idx[k])

    return {
        "new": [today_idx[k] for k in new_keys],
        "escalated": escalated,
        "improved": improved,
        "resolved": [yest_idx[k] for k in resolved_keys],
        "unchanged": unchanged,
    }


def _is_worse(today_status: str, yest_status: str) -> bool:
    rank = {
        "Resolved": 0,
        "Available with limitations": 1,
        "Current": 2,
        "To Be Discontinued": 3,
        "Discontinued": 3,
    }
    return rank.get(today_status, 1) > rank.get(yest_status, 1)
```

## Severity classification

Two layers: **rule-based pre-filter** + **LLM-explained rationale**.

### Rule-based pre-filter

Cheap, deterministic, runs in milliseconds. Filters obvious cases:

```python
def classify_severity(item: dict, orders: dict, formulary_entry: dict) -> str:
    # Resolved bucket — already known
    if item.get("_diff_bucket") == "resolved":
        return "Resolved"

    order_count = orders.get("count_last_30_days", 0)
    has_alt = len(formulary_entry.get("preferred_alternatives", [])) > 0
    is_iv_only = formulary_entry.get("route_of_administration") == "IV"
    is_restricted = formulary_entry.get("restriction_criteria") is not None

    # Critical: high-volume + no alt + restrictive route
    if order_count > 10 and not has_alt and (is_iv_only or is_restricted):
        return "Critical"
    # Critical: any volume + escalated status
    if item.get("_diff_bucket") == "escalated" and order_count > 0:
        return "Critical"
    # Watch: volume > 0 with alternative
    if order_count > 0:
        return "Watch"
    # No active orders → low priority Watch
    return "Watch"
```

### LLM rationale

For each rule-classified item, the agent generates a one-sentence rationale + checks the rule's classification. If the LLM disagrees (rare), it can suggest override with reason.

System prompt instruction:
> "Severity already pre-classified by rules. Your job: confirm or override with explanation. Override only if rule missed clinical context (e.g., contraindication for the only formulary alternative). Format: `{severity, rationale, rule_overridden: bool}`."

## BriefingItem schema

```python
{
    "item_id": "uuid",
    "rxcui": "11124",
    "drug_name": "Cisplatin",
    "severity": "Critical",
    "summary": "Cisplatin shortage continues, with 23 active orders in Oncology and no available alternative on formulary.",
    "rationale": "...",
    "alternatives": [
        {
            "rxcui": "40048",
            "name": "Carboplatin",
            "rationale": "Same ATC class L01XA, IV route match, on formulary as preferred",
            "source_url": "...",
            "confidence": "medium"
        }
    ],
    "citations": [
        {"claim": "Currently in shortage per FDA", "source_url": "https://api.fda.gov/drug/shortages.json?search=openfda.rxcui:11124"},
        {"claim": "Carboplatin in same class", "source_url": "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui=11124"}
    ],
    "confidence": "high",
    "recommended_action": "Switch new orders to carboplatin pending P&T review",
    "user_action": null,                # set on accept/override/escalate
    "user_action_timestamp": null
}
```

## BriefingRun schema

```python
{
    "run_id": "uuid",
    "run_timestamp": "2026-04-30T08:00:00Z",
    "customer_id": "memorial-health-450",
    "prompt_version": "v1",
    "items_reviewed": 12,
    "items_surfaced": 8,
    "tool_calls": [
        {"timestamp": "...", "server": "fda_shortage", "tool": "get_shortage_detail", "args": {...}, "duration_ms": 245}
    ],
    "total_tokens_used": 18432,
    "total_cost_usd": 0.087,
    "latency_ms": 47200,
    "items": [BriefingItem, ...]
}
```

## What can go wrong

- **Diff drift**: if yesterday_snapshot.json is regenerated by mistake, today's "new" bucket disappears. Mitigation: only generate yesterday_snapshot if file missing.
- **Empty briefing**: formulary doesn't overlap today's shortages. Mitigation: H1 builds formulary FROM live shortages. Verify overlap >5 at H1 exit.
- **Status string canonical values**: FDA `status` field actual values are `Current`, `To Be Discontinued`, `Resolved` (verified 2026-05-01 via openFDA `count=status`). Earlier POC used `"Currently in Shortage"` — wrong. v0.1 filters to `status:Current`. TBD handling = open question (see QUESTIONS-FOR-ANTON.md Q1).
- **Severity rule-based undercounts**: drug with 0 orders but historically critical (e.g., methotrexate IV) gets "Watch". Acceptable for v0.1 — eval set will catch if it's a real issue.
- **Alt confidence inflation**: LLM marks class-member as "high confidence equivalent". Mitigation: rule-based ceiling — class-member alts cap at "medium".
