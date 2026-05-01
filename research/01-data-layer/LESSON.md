# Data Layer — Lesson

## What this layer owns

Three real public APIs + three synthetic data files + one diff seed.

| Source | Type | Use |
|--------|------|-----|
| openFDA Drug Shortages (`api.fda.gov/drug/shortages.json`) | Real, no auth | Live shortage feed |
| openFDA Drug Label (`api.fda.gov/drug/label.json`) | Real, no auth | Indications, contraindications, alternatives info — RAG corpus |
| RxNorm + RxClass (`rxnav.nlm.nih.gov/REST/`) | Real, no auth | Name normalization (RxNorm) + therapeutic alternatives proxy (RxClass) |
| `data/synthetic_formulary.json` | Synthetic | 30 drugs, formulary status, route, preferred alts |
| `data/active_orders.json` | Synthetic | Order volume per drug × department |
| `data/yesterday_snapshot.json` | Synthetic | Seed for diff logic |

## Why synthetic, why real

PRD §11.2 + §9.4 explicitly defer real customer formulary integration. v0.1 demonstrates the pattern with synthetic data labeled as such (Principle 7).

Live APIs prove the pattern works against real-world data shape, rate limits, and citation defensibility — the whole point of "citation-first trust."

## The overlap problem

If synthetic formulary doesn't overlap live FDA shortages, briefing is empty. Demo dies.

**Solution**: at H1, fetch live shortages once, pick 30 RxCUIs from the feed, build formulary FROM that list. Guarantees overlap on demo day.

## RxNorm vs RxClass — the trap

RxNorm normalizes drug names → RxCUI codes. **RxNorm does NOT return therapeutic alternatives.** `getRelatedByType` returns brand/generic/form variations only (e.g., "Tylenol" ↔ "acetaminophen"), not real alternatives ("cisplatin" → "carboplatin").

**RxClass** is the right API for alternatives-as-class-membership:
- `/class/byRxcui?rxcui=...&relaSource=ATC` → ATC therapeutic class
- `/classMembers?classId=...&relaSource=ATC` → all drugs in that class

Filter the class member list by:
1. Same `route_of_administration` (don't suggest oral if shortage is IV-only)
2. Not also in shortage (filter against current FDA feed)
3. On formulary (preferred status > non-formulary)

This is **proxy** for therapeutic equivalence, not true clinical equivalence. Label it as such — confidence stays "medium" not "high" for class-member-only matches.

## openFDA Label structure

Each label record ~15-18 KB JSON. Sections that matter for shortage briefings:

| Section | Why we care |
|---------|-------------|
| `indications_and_usage` | What is this drug FOR (informs alternative routing) |
| `dosage_and_administration` | Dosing equivalence between alternatives |
| `contraindications` | Critical safety info |
| `warnings` / `boxed_warning` | Safety severity |
| `drug_interactions` | Cross-drug concerns |
| `clinical_pharmacology` | MOA — confirms class membership clinically |
| `how_supplied` | Forms, strengths, NDCs |

Full label has 30+ fields, most empty or irrelevant. Trim aggressively.

## Yesterday snapshot — fictional but real-shaped

There's no actual "yesterday" data because we just started. Generate a snapshot that's a deliberate edit of today's live FDA feed:

- Remove 2 records → today shows them as new "Resolved" (no longer in shortage feed... actually inverse — they were in yesterday but not today = resolved)
- Wait, re-think: if a drug was in shortage *yesterday* and is *not* in shortage today → resolved. So "remove from yesterday" doesn't model that. Correct model:
  - 2 drugs in yesterday's `current` status that are NOT in today's feed → **resolved** today
  - 2 drugs in today's feed that were NOT in yesterday → **new shortage**
  - 2 drugs in both with different status (e.g., yesterday=available-with-restrictions, today=current-shortage) → **escalated**

Implementation: take today's FDA feed → make a copy → add 2 fake records (will become "resolved" tomorrow when they aren't in the live feed) → remove 2 records (will become "new" today since they're in live but not yesterday) → flip status on 2 (will become "escalated"). Save as yesterday_snapshot.json.

## File-on-disk shape

`data/synthetic_formulary.json`:
```json
{
  "customer_id": "memorial-health-450",
  "label": "SYNTHETIC — for v0.1 demo only",
  "generated_at": "2026-04-30T08:00:00Z",
  "drugs": [
    {
      "rxcui": "11124",
      "name": "Cisplatin",
      "formulary_status": "preferred",
      "route_of_administration": "IV",
      "therapeutic_class": "Antineoplastic",
      "restriction_criteria": "Oncology only",
      "preferred_alternatives": ["carboplatin"],
      "last_pt_review_date": "2026-01-15"
    }
    // ... 29 more
  ]
}
```

`data/active_orders.json`:
```json
{
  "customer_id": "memorial-health-450",
  "snapshot_date": "2026-04-30",
  "orders": [
    {
      "rxcui": "11124",
      "count_last_30_days": 23,
      "departments": ["Oncology", "Surgery"]
    }
    // ...
  ]
}
```

## Cache discipline

Every API call goes through `cache.py` (see `research/03b-caching/`). Don't bypass — rate limits will bite.

## What can go wrong

- **openFDA returns 404** for a real RxCUI. Fallback: try `generic_name` search.
- **RxClass returns no class for some drugs.** Fallback: skip alternatives, surface "no class-based alternatives found."
- **FDA shortage record has no RxCUI.** It happens (~10%). Fallback: match on `generic_name` + `dosage_form`.
- **Yesterday snapshot drift**: re-running data_loader regenerates yesterday snapshot, breaking diff. Mitigation: only regenerate if file missing.
